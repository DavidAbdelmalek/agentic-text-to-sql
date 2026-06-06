-- Clean the messy real data into well-formed SALES lines (the "T" the repo shows).
-- Snowflake dialect: TRY_TO_* validates dirty strings without regex escaping; non-numeric or
-- blank values become NULL and are filtered. Drop cancellations (invoice 'C...'), non-positive
-- quantity (returns/adjustments), non-positive price, and rows with no numeric customer id.
with src as (
    select * from {{ source('raw', 'online_retail') }}
),

valid as (
    select
        invoice                        as invoice_no,
        stock_code,
        nullif(trim(description), '')  as description,
        invoice_date,
        quantity,
        price,
        customer_id,
        trim(country)                  as country
    from src
    where invoice not like 'C%'                       -- not a cancellation
      and try_to_number(quantity) is not null         -- integer-shaped
      and try_to_double(price) is not null             -- numeric-shaped
      and try_to_number(customer_id) is not null       -- a real customer id
      and stock_code is not null
)

select
    invoice_no,
    stock_code,
    description,
    to_timestamp(invoice_date)                                      as invoice_ts,
    try_to_number(quantity)::int                                   as quantity,
    round(try_to_double(price)::number(12, 2), 2)                  as unit_price_gbp,
    split_part(customer_id, '.', 1)::int                          as customer_id,
    country,
    round((try_to_number(quantity) * try_to_double(price))::number(18, 2), 2) as line_revenue_gbp
from valid
-- Compare the ROUNDED price so sub-cent prices that round to 0.00 are dropped.
where try_to_number(quantity)::int > 0
  and round(try_to_double(price)::number(12, 2), 2) > 0

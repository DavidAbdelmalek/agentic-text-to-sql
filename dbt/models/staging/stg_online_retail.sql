-- Clean the messy real data into well-formed SALES lines. This is the "T" the repo shows:
-- real Online Retail II is full of cancellations, returns, blank customers, and junk codes.
--
-- Filters (each defensible): drop cancellations (invoice 'C...'), non-positive quantity
-- (returns/adjustments), non-positive price, and rows with no numeric customer id (can't
-- attribute to a customer dimension). Casting happens AFTER regex validation so a bad value
-- can never blow up a ::int / ::numeric cast.
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
    where invoice !~ '^C'                              -- not a cancellation
      and quantity ~ '^-?[0-9]+$'                      -- integer-shaped
      and price ~ '^[0-9]+(\.[0-9]+)?$'                -- numeric-shaped
      and customer_id ~ '^[0-9]+(\.[0-9]+)?$'          -- a real customer id
      and stock_code is not null
)

select
    invoice_no,
    stock_code,
    description,
    invoice_date::timestamp                              as invoice_ts,
    quantity::int                                        as quantity,
    price::numeric(12, 2)                                as unit_price_gbp,
    split_part(customer_id, '.', 1)::int                 as customer_id,
    country,
    round((quantity::int * price::numeric)::numeric, 2)  as line_revenue_gbp
from valid
-- Compare the ROUNDED price so sub-cent prices (e.g. 0.001) that round to 0.00 under
-- numeric(12,2) are dropped, not kept as zero-priced lines.
where quantity::int > 0
  and round(price::numeric, 2) > 0

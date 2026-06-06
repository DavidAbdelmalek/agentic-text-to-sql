-- Sales fact. Grain: one invoice line. Measures in GBP.
-- Surrogate FKs use the SAME generate_surrogate_key() inputs as the dimensions so the
-- relationships tests line up. Region resolved via the customer's country.
with orders as (
    select * from {{ ref('stg_online_retail') }}
)

select
    row_number() over (
        order by o.invoice_no, o.stock_code, o.invoice_ts, o.customer_id, o.quantity, o.unit_price_gbp
    )                                                              as sales_key,
    o.invoice_no,
    to_char(o.invoice_ts::date, 'YYYYMMDD')::int                  as date_key,
    {{ dbt_utils.generate_surrogate_key(['o.customer_id']) }}     as customer_key,
    {{ dbt_utils.generate_surrogate_key(['o.stock_code']) }}      as product_key,
    {{ dbt_utils.generate_surrogate_key(['o.country']) }}         as country_key,
    o.quantity,
    o.unit_price_gbp,
    o.line_revenue_gbp                                            as revenue_gbp
from orders o

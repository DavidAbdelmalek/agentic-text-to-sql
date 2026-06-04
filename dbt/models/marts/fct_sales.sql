-- Sales fact. Grain: one invoice line. Measures in GBP.
-- The raw data has no line id and contains genuine duplicate lines, so sales_key is a
-- deterministic row_number over a total ordering (identical rows are interchangeable).
-- Surrogate FKs use the SAME generate_surrogate_key() inputs as the dimensions, so the
-- relationships tests line up.
with s as (
    select * from {{ ref('stg_online_retail') }}
)

select
    row_number() over (
        order by invoice_no, stock_code, invoice_ts, customer_id, quantity, unit_price_gbp
    )                                                              as sales_key,
    invoice_no,
    to_char(invoice_ts::date, 'YYYYMMDD')::int                    as date_key,
    {{ dbt_utils.generate_surrogate_key(['customer_id']) }}       as customer_key,
    {{ dbt_utils.generate_surrogate_key(['stock_code']) }}        as product_key,
    {{ dbt_utils.generate_surrogate_key(['country']) }}           as country_key,
    quantity,
    unit_price_gbp,
    line_revenue_gbp                                              as revenue_gbp
from s

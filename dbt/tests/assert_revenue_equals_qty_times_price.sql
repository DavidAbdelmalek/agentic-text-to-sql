-- Singular data test: revenue must equal quantity * unit price (within rounding).
-- Passes when zero rows are returned.
select
    sales_key,
    quantity,
    unit_price_gbp,
    revenue_gbp
from {{ ref('fct_sales') }}
where abs(revenue_gbp - (quantity * unit_price_gbp)) > 0.01

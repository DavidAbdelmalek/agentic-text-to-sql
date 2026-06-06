-- Product dimension (grain: one row per stock code). A stock code maps to several
-- descriptions in the raw data (typos, '?', case variants); pick the modal description.
with per_product as (
    select
        stock_code,
        mode(description) as product_name
    from {{ ref('stg_online_retail') }}
    where description is not null
    group by stock_code
)

select
    {{ dbt_utils.generate_surrogate_key(['stock_code']) }} as product_key,
    stock_code,
    product_name
from per_product

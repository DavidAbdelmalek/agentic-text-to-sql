-- Customer dimension (grain: one row per customer). A customer can appear with more than
-- one country across invoices; take the modal country (deterministic via mode()).
with per_customer as (
    select
        customer_id,
        mode() within group (order by country) as country
    from {{ ref('stg_online_retail') }}
    group by customer_id
)

select
    {{ dbt_utils.generate_surrogate_key(['customer_id']) }} as customer_key,
    customer_id,
    country
from per_customer

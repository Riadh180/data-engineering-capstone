select pr_author_class,
       count(*) as n_reviews,
       round(avg((state='changes_requested')::int)::numeric,4) as changes_requested_rate
from {{ source('silver','gh_pr_reviews') }}
group by pr_author_class
order by pr_author_class

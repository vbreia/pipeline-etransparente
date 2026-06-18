#!/usr/bin/env python3
import os
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, Dimension, Metric, DateRange, OrderBy

def main():
    property_id = os.getenv("GA4_PROPERTY_ID")
    if not property_id:
        raise RuntimeError("Defina GA4_PROPERTY_ID no ambiente")

    client = BetaAnalyticsDataClient()

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[
            Dimension(name="pagePath"),
            Dimension(name="pageTitle"),
        ],
        metrics=[
            Metric(name="screenPageViews"),
        ],
        date_ranges=[
            DateRange(start_date="30daysAgo", end_date="today"),
        ],
        order_bys=[
            OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                desc=True,
            )
        ],
        limit=50,  # top 50 páginas
    )

    response = client.run_report(request)

    print("PAGE PATH                          | PAGE TITLE                        | VIEWS")
    print("-------------------------------------------------------------------------------")
    for row in response.rows:
        path = row.dimension_values[0].value or "(sem caminho)"
        title = row.dimension_values[1].value or "(sem título)"
        views = row.metric_values[0].value or "0"
        if "/oscs/" in path:
            print(f"{path[:30]:30} | {title[:30]:30} | {views}")

if __name__ == "__main__":
    main()

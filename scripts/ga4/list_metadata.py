#!/usr/bin/env python3
import os
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import GetMetadataRequest

def main():
    property_id = os.getenv("GA4_PROPERTY_ID")
    if not property_id:
        raise RuntimeError("Defina GA4_PROPERTY_ID no ambiente")

    client = BetaAnalyticsDataClient()

    # metadata global da propriedade
    name = f"properties/{property_id}/metadata"

    metadata = client.get_metadata(request=GetMetadataRequest(name=name))

    print("=== DIMENSÕES ===")
    for d in metadata.dimensions:
        print(f"- {d.api_name}  |  {d.ui_name}")

    print("\n=== MÉTRICAS ===")
    for m in metadata.metrics:
        print(f"- {m.api_name}  |  {m.ui_name}")

if __name__ == "__main__":
    main()

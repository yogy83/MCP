#!/usr/bin/env python3
import os
import json
import requests

BASE = os.getenv("TEMENOS_BASE_URL", "http://172.16.204.40:8280/irf-provider-container/api")

def fetch_and_print(name: str, url: str):
    print(f"\n=== {name} ===")
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error fetching {name}: {e}")

def main():
    account_id = "105929"
    customer_id = "100210"

    endpoints = [
        ("Transactions",
         f"{BASE}/v1.0.0/holdings/accounts/{account_id}/transactions"),
        ("Customer Accounts",
         f"{BASE}/v1.0.0/party/customers/{customer_id}/arrangements"),
        ("Account Balance",
         f"{BASE}/v1.0.0/holdings/accounts/{account_id}")
    ]

    for name, url in endpoints:
        fetch_and_print(name, url)

if __name__ == "__main__":
    main()

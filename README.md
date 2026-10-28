# dev-journal

![Release](https://img.shields.io/github/v/release/andrea-tonello/portfolio-manager-gui)
![License](https://img.shields.io/github/license/andrea-tonello/portfolio-manager-gui)
![Downloads](https://img.shields.io/github/downloads/andrea-tonello/portfolio-manager-gui/total)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Build](https://github.com/andrea-tonello/portfolio-manager-gui/actions/workflows/build-release.yml/badge.svg)

This development branch focuses on implementing a non-chronological insertion mechanism for operations.

The idea is to migrate to a journal-based system, where we store what the user did, not what it resulted in:
- An operations journal as the source of truth, instead of the CSV
- The ledger CSVs become a by-product of the journal
- One journal per account, something like:

```
{"version": 1,
 "operations": [
   {"id": "a1f3…", "seq": 1, "date": "2025-03-04", "kind": "deposit", "amount": 10000.0},
   {"id": "b7c2…", "seq": 2, "date": "2025-03-05", "kind": "buy", "ticker": "ISP.MI",
    "asset_name": "Intesa Sanpaolo", "product": "Stock", "currency": "EUR", "conv_rate": 1.0,
    "quantity": 1000, "price": 3.9, "fee": 2.95, "fee_mode": "abp", "tax_rate": 0.26, "ter": null},
   {"id": "c9d4…", "seq": 3, "date": "2025-06-10", "kind": "transfer_out", "amount": 100.0,
    "counterpart": "BG Saxo", "transfer_id": "e5f6…"}
 ]}
```
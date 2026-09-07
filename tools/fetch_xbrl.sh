#!/bin/sh
# Fetch REAL XBRL facts from SEC EDGAR (public domain, permitted source).
# One concept per company. A contact-bearing User-Agent is mandatory: SEC
# returns 403 without one, and that is their stated condition of access.
UA="marfin-llm/0.1 (contact@example.com)"
OUT=/tmp/r20/raw
mkdir -p "$OUT"

fetch() {
  cik="$1"; tag="$2"; name="$3"
  if [ -f "$OUT/$name.json" ]; then echo "  cached $name"; return; fi
  curl -sS --max-time 45 -H "User-Agent: $UA" \
    "https://data.sec.gov/api/xbrl/companyconcept/CIK$cik/us-gaap/$tag.json" \
    -o "$OUT/$name.json"
  sz=$(stat -c%s "$OUT/$name.json" 2>/dev/null || echo 0)
  echo "  $name -> $sz bytes"
  sleep 1
}

# Apple 0000320193, Microsoft 0000789019, Alphabet 0001652044,
# Johnson & Johnson 0000200406, Walmart 0000104169
fetch 0000320193 NetIncomeLoss                aapl_netincome
fetch 0000320193 Assets                        aapl_assets
fetch 0000320193 StockholdersEquity            aapl_equity
fetch 0000789019 RevenueFromContractWithCustomerExcludingAssessedTax msft_revenue
fetch 0000789019 NetIncomeLoss                msft_netincome
fetch 0000789019 Assets                        msft_assets
fetch 0001652044 RevenueFromContractWithCustomerExcludingAssessedTax goog_revenue
fetch 0001652044 NetIncomeLoss                goog_netincome
fetch 0000200406 RevenueFromContractWithCustomerExcludingAssessedTax jnj_revenue
fetch 0000200406 NetIncomeLoss                jnj_netincome
fetch 0000104169 Revenues                      wmt_revenues
fetch 0000104169 NetIncomeLoss                wmt_netincome
echo "done"

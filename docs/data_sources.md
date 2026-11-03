# Verified public datasets and acquisition

## Electronics store event logs — REES46

Official REES46 listing: https://data.rees46.com/

Official direct download (gzip, ~20 MB):
https://data.rees46.com/datasets/electronics-events/electronics-events.csv.gz

Kaggle landing page:
https://www.kaggle.com/datasets/mkechinov/ecommerce-events-history-in-electronics-store

Save the original gzip to `data/raw/electronics-events.csv.gz`. Do not unzip: pandas reads `.csv.gz` directly. Do not commit the raw download by default. Mention REES46 and the Kaggle source when publishing analysis. The source is event-level and does not contain a reliable order identifier, advertising costs, cost of goods, or marketplace commissions.

## MineThatData e-mail analytics experiment — Kevin Hillstrom

Original publication:
https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html

Historical direct CSV:
https://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv

Alternative documentation and loader:
https://www.tensorflow.org/datasets/catalog/hillstrom

Kaggle mirror:
https://www.kaggle.com/datasets/bofulee/kevin-hillstrom-minethatdata-e-mailanalytics

Save the original CSV as `data/raw/hillstrom.csv`. Preserve its field names and all three experimental arms. Do not commit the raw download by default; original redistribution license must be reviewed separately from public accessibility. Cite Kevin Hillstrom / MineThatData in any published analysis.


## Provenance of the published results

The results in the README and `examples/real_report.html` were computed from the original files obtained from the sources above (REES46 `electronics-events.csv.gz`, Hillstrom `hillstrom.csv`). The pipeline validates schema but cannot verify file origin, hence the notice in the report header.

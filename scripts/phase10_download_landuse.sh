set -e
cd "$(dirname "$0")/../data/raw/landuse"
V=GFC-2024-v1.12
for t in 10N_070E 10N_090E 20N_070E 20N_080E 20N_090E 30N_060E 30N_070E 30N_080E 30N_090E 40N_070E 40N_080E; do
  for l in treecover2000 lossyear datamask; do
    f=hansen/Hansen_${V}_${l}_${t}.tif
    [ -s "$f" ] || curl -sf --retry 3 -o "$f" "https://storage.googleapis.com/earthenginepartners-hansen/$V/Hansen_${V}_${l}_${t}.tif"
  done
  echo "hansen $t done"
done
G=https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL
[ -s ghsl/built.zip ] || curl -sfL --retry 3 -o ghsl/built.zip $G/GHS_BUILT_S_GLOBE_R2023A/GHS_BUILT_S_E2020_GLOBE_R2023A_4326_30ss/V1-0/GHS_BUILT_S_E2020_GLOBE_R2023A_4326_30ss_V1_0.zip
[ -s ghsl/pop.zip ] || curl -sfL --retry 3 -o ghsl/pop.zip $G/GHS_POP_GLOBE_R2023A/GHS_POP_E2020_GLOBE_R2023A_4326_30ss/V1-0/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0.zip
echo DOWNLOADS_DONE

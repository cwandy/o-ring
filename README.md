# O-Ring / Conta Yuvası Tasarım Programı

Statik o-ring yuvası tasarımı, kontrolü ve standart ölçü önerisi için mühendislik aracı.
Odak alanı kriyojenik itki sistemleri (LOX, LN2, LH2, LCH4). Proje tanımı ve alınan kararlar `SPEC.md` dosyasında; §13'teki kararlar önceki bölümlerin önüne geçer.

## Kurulum ve çalıştırma

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run streamlit run app/streamlit_app.py
```

## Sayfalar

| Sayfa | İşlev |
|---|---|
| Yuva Kontrol | Mevcut bir piston, rod veya face yuvasını tek noktada ve sıcaklık taraması boyunca kontrol eder; squeeze/doluluk ve boşluk grafikleri, kesit görünümü |
| Tolerans Analizi | Worst-case, RSS ve Monte Carlo analizi; histogramlar, geçme oranları, duyarlılıklar |
| Ölçü Öner | AS568 ve ISO 3601-1 o-ringleri tarar, her biri için yuvayı tasarlayıp doğrular ve sıralar |
| Yaylı Conta | Katalog ölçüleriyle yaylı conta (PTFE/PCTFE ceket) için termal sıkışma ve boşluk kontrolü |

Her sayfada rapor (PDF ve Markdown ZIP) ile DXF yuva profili indirilebilir. Örnekler: `docs/ornek_rapor.pdf`, `docs/ornek_yuva_profili.dxf`.

## Veri

`data/` altında malzeme, akışkan, kural ve standart ölçü tabloları bulunur. Her değerin bir kaynağı (`data/references.yaml`) ve bir veri kalitesi etiketi var. Kaynağın nasıl çıkarıldığı `docs/data_provenance.md` dosyasında anlatılıyor.

Doğrulanması gereken verilerin listesi:

```bash
uv run python -m oring_designer.verify
```

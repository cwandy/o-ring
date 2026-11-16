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

Masaüstü programı (asıl arayüz):

```bash
uv run python desktop/main.py
```

Tarayıcı sürümü (yalnızca geliştirme):

```bash
uv run streamlit run app/streamlit_app.py
```

Python'suz Windows paketi (`dist/o-ring-windows-x64-*.zip`, içinde `O-Ring.exe`):

```bash
uv run python tools/build_windows_offline.py
```

## Sayfalar

Her sayfada girdiler solda, ölçülü yuva şeması sağda, sonuçlar altta.

| Sayfa | İşlev |
|---|---|
| Yuva Hesaplayıcı | Malzeme, kesit, sıcaklık ve basınçtan yuva derinliği/genişliği, toleranslar, sıcaklıkla değişim ve gereken kuvvet |
| Yuva Kontrol | Mevcut bir piston, rod veya face yuvasını kontrol eder: çalışma noktası, sıcaklık taraması, tolerans analizi (ISO 286 sınıfları veya özel sapmalar; worst-case, RSS, Monte Carlo), kesit görünümü, rapor/DXF |
| Ölçü Öner | AS568 ve ISO 3601-1 o-ringleri tarar, her biri için yuvayı tasarlayıp doğrular ve sıralar |
| Yaylı Conta | Katalog ölçüleriyle yaylı conta (PTFE/PCTFE ceket) için termal sıkışma ve boşluk kontrolü |

Her sayfada rapor (PDF ve Markdown ZIP) ile DXF yuva profili indirilebilir. Örnekler: `docs/ornek_rapor.pdf`, `docs/ornek_yuva_profili.dxf`.

## Veri

`data/` altında malzeme, akışkan, kural ve standart ölçü tabloları bulunur. Her değerin bir kaynağı (`data/references.yaml`) ve bir veri kalitesi etiketi var. Kaynağın nasıl çıkarıldığı `docs/data_provenance.md` dosyasında anlatılıyor.

Doğrulanması gereken verilerin listesi:

```bash
uv run python -m oring_designer.verify
```

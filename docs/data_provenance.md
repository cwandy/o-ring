# Veri kökeni (Faz 1)

Termal büzülme verilerinin nereden ve nasıl alındığı. Kaynak künyeleri: `data/references.yaml`.
Doğrulanacak maddelerin güncel listesi: `uv run python -m oring_designer.verify`.

| Malzeme | Kaynak | Aralık | data_quality |
|---|---|---|---|
| Al 6061-T6, Al 3003 | NIST TRC eğri uydurması (iki alaşımda aynı katsayılar) | 4–300 K | measured_reference |
| SS 304, SS 316 | NIST TRC eğri uydurması (iki alaşımda aynı katsayılar) | 4–300 K | measured_reference |
| Inconel 718 | NIST TRC eğri uydurması | 4–300 K | measured_reference |
| Al 7075-T6 | NBS Monograph 29, Tablo 3.2 (3 nokta) | 116–293 K | literature |
| Al 1100 | Saf Al, NBS Monograph 29 Tablo 2.1 (temsilci, kullanıcı onayı) | 20–300 K | literature |
| PCTFE | NBS Monograph 29, Tablo 2.4 (Fluorothene / Kel-F) | 20–300 K | literature |
| VMQ | NBS Monograph 29, Tablo 2.4 (Silastic 160, tek compound) | 20–300 K | literature |
| PTFE | Monograph 29 Tablo 2.4 + Kirby (1956) Şekil 2 ve Tablo 2 | 20–423 K | 20–60 K extrapolated, diğerleri literature |
| NBR, EPDM, FKM, FFKM, PVMQ, PH çelikler | — | — | veri yok (K3) |

Monograph 29 tabloları, OCR çıktısına ek olarak sayfa görüntüleriyle tek tek karşılaştırılarak girildi.

## PTFE geçiş bölgesi

Kirby (1956), 19–20 °C ve 30 °C geçişlerini yalnızca Şekil 2'de (0–110 °C) veriyor. Şekil 600 dpi
çözünürlükte sayısallaştırıldı (`tools/digitize_kirby1956_fig2.py`):

- Eksenler çerçevedeki tik işaretlerinden kalibre edildi. Sayfa eğikliği sol ve sağ tikler arasında enterpolasyonla düzeltildi.
- 28 °C üstünde iz, kübik uydurmayla değiştirildi (RMS kalıntı 0.003 %; veri işaretçisi artefaktları temizlendi).
- Sonuç Kirby Tablo 2 değerlerine çapalandı (0, 25, 50 ve 100 °C). En büyük düzeltme 0 °C'de −0.0185 %.
- Kontrol görseli: `docs/ptfe_digitization_check.png`. Kırmızı daireler sayısallaştırılan noktaları, mavi kareler Tablo 2 çapalarını gösteriyor.

Not: Gerilmeli (tavlanmamış) PTFE'nin genleşmesi %20'ye kadar farklı olabilir (Kirby 1956).

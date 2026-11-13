# Veri kökeni

Termal büzülme verilerinin nereden ve nasıl alındığı. Kaynak künyeleri: `data/references.yaml`.
Doğrulanacak maddelerin güncel listesi: `uv run python -m oring_designer.verify`.

| Malzeme | Kaynak | Aralık | data_quality |
|---|---|---|---|
| Al 6061-T6 | NIST TRC (4–300 K) + Bal Seal TR-18 (100 °C) | 4–373 K | measured_reference / vendor |
| Al 3003 | NIST TRC (6061 ile aynı katsayılar) + 100 °C'de 6061 değeri vekil | 4–373 K | measured_reference / extrapolated |
| Al 7075-T6 | 116 K altı: NIST 6061 eğrisi Monograph değerine ölçeklendi; 116–293 K NBS Monograph 29 Tablo 3.2; 100 °C Bal Seal | 20–373 K | extrapolated / literature / vendor |
| Al 1100 | Saf Al, NBS Monograph 29 Tablo 2.1 (temsilci, kullanıcı onayı) + 100 °C'de 6061 değeri vekil | 20–373 K | literature / extrapolated |
| SS 304 | NIST TRC (4–300 K) + Bal Seal TR-18 (93, 205, 316 °C) | 4–589 K | measured_reference / vendor |
| SS 316 | NIST TRC (304 ile aynı katsayılar) + 300 K üstü 304 değeri vekil | 4–589 K | measured_reference / extrapolated |
| Inconel 718 | NIST TRC eğri uydurması | 4–300 K | measured_reference |
| 17-4 PH | 200 K altı: NIST Fe-9Ni eğrisi Clark (1968) yöntemiyle ölçeklendi (×0.980); −73…93 °C Bal Seal; 474 ve 568 K Sandia SAND80-2302 (döküm 17-4) | 20–568 K | extrapolated / vendor / literature |
| 15-5 PH | 17-4 ile aynı tahmin; −73…93 °C Bal Seal | 20–366 K | extrapolated / vendor |
| 17-7 PH (sertleştirilmiş) | Fe-9Ni eğrisi ×0.998; 0…316 °C Bal Seal "17-7 PH H900" satırı. Condition A (östenitik) kapsanmıyor | 20–589 K | extrapolated / vendor |
| PCTFE | NBS Monograph 29, Tablo 2.4 (Fluorothene / Kel-F). Daikin NEOFLON broşürü (Tablo 3) ile kontrol: 293→83 K ~%1.03 vs Monograph %0.96 | 20–300 K | literature |
| VMQ | NBS Monograph 29 (Silastic 160) + 191 °C Parker Tablo 2-5 "Silicone" | 20–464 K | literature |
| PTFE | Monograph 29 Tablo 2.4 + Kirby (1956) Şekil 2 ve Tablo 2 | 20–423 K | 20–60 K extrapolated, diğerleri literature |
| NBR, EPDM, FKM | Parker ORD 5700 Tablo 2-5 (−54 °C / 24 °C / 191 °C, aile ortalaması) | 219–464 K | literature |
| PVMQ | Parker Tablo 2-5 "Low-temperature type silicone" | 219–464 K | literature |
| FFKM | Parker (Parofluor) doğrusal katsayı 1.8e-4 /°F | 255–593 K | literature |

Diğer kaynaklı değerler (2026-11-13): PTFE üst kullanım sıcaklığı 260 °C (Chemours Teflon PTFE 6C X);
PCTFE sertlik D80 (Daikin M-300P); PH çelikler için kriyojenik tokluk uyarısı 0 °C altı ve hidrojen
gevrekleşmesi (Sandia SAND2012-7321 bölüm 1700/1810), Inconel 718 hidrojen bayrağı (aynı rapor,
bölüm 2301); MMH ve N2H4 kaynama noktaları ve kriyojen kaynama noktaları (NIST WebBook, doyma
verisinden 101.325 kPa'da kontrol edildi).

Tahmin yöntemi (extrapolated): Clark, A.F., Cryogenics 8 (1968) 282 / AEC-NASA Tech Brief B69-10707 —
oda sıcaklığı genleşme katsayısı, düşük sıcaklığa toplam büzülmenin iyi bir göstergesidir; ısıl işlem,
yapı değişmedikçe etkisizdir. Bu nedenle tüm ısıl işlem durumları (H900…H1150, T6/T651/T73…) aynı
eğriyi kullanır. Türetme aritmetiği: `tools/derive_thermal_data.py`.

Açık kaynak bulunamayanlar: PCTFE 300 K üstü genleşme ve üst kullanım sıcaklığı; Inconel 718 300 K
üstü; NTO ve RP-1 kaynama noktası (bilgi amaçlı, hesapta kullanılmıyor).

Monograph 29 tabloları, OCR çıktısına ek olarak sayfa görüntüleriyle tek tek karşılaştırılarak girildi.

## PTFE geçiş bölgesi

Kirby (1956), 19–20 °C ve 30 °C geçişlerini yalnızca Şekil 2'de (0–110 °C) veriyor. Şekil 600 dpi
çözünürlükte sayısallaştırıldı (`tools/digitize_kirby1956_fig2.py`):

- Eksenler çerçevedeki tik işaretlerinden kalibre edildi. Sayfa eğikliği sol ve sağ tikler arasında enterpolasyonla düzeltildi.
- 28 °C üstünde iz, kübik uydurmayla değiştirildi (RMS kalıntı 0.003 %; veri işaretçisi artefaktları temizlendi).
- Sonuç Kirby Tablo 2 değerlerine çapalandı (0, 25, 50 ve 100 °C). En büyük düzeltme 0 °C'de −0.0185 %.
- Kontrol görseli: `docs/ptfe_digitization_check.png`. Kırmızı daireler sayısallaştırılan noktaları, mavi kareler Tablo 2 çapalarını gösteriyor.

Not: Gerilmeli (tavlanmamış) PTFE'nin genleşmesi %20'ye kadar farklı olabilir (Kirby 1956).

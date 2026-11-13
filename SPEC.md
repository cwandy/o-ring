# O-Ring / Conta Yuvası Tasarım Programı — Proje Tanımı (Claude Code için)

Bu dosya projenin ana tanımıdır. Her oturumun başında bu dosyayı oku. Fazlar sırayla ilerler. Her fazın sonunda dur, ne yaptığını özetle ve onayımı bekle.

## 1. Bağlam

- Kullanıcı: Uzay itki sistemlerinde valf ve sıvı itki tarafında çalışan bir mühendis. Ana kullanım alanı **kriyojenik** (LOX, LN2, LH2, LCH4).
- Amaç: Statik (ve ileride dinamik) conta yuvası tasarımı, kontrolü ve standart ölçü önerisi yapan bir mühendislik aracı.
- Sızdırmazlık malzemeleri: NBR, EPDM, FKM, FFKM, Silikon (VMQ / fenil silikon PVMQ), PTFE, PCTFE.
- Gövde malzemeleri: Al 6061-T6, Al 7075-T6, Al 1000 serisi (1100 temsilci), Al 3000 serisi (3003 temsilci), SS 304, SS 316, 17-4 PH, 15-5 PH, 17-7 PH, Inconel 718.
  - Not: Kullanıcı "17-5 PH" yazdı. Böyle yaygın bir alaşım bilinmiyor, büyük olasılıkla 17-7 PH kastediliyor. Veri dosyasına 17-7 PH olarak ekle ve `notes` alanına bu notu yaz.

## 2. Temel ilkeler (kesin kurallar)

1. **Veri uydurma yok.** Her sayısal malzeme verisinin bir `source` alanı ve bir `data_quality` alanı olacak. `data_quality` değerleri şunlardan biri: `measured_reference`, `literature`, `extrapolated`, `placeholder`.
   - Emin olmadığın değeri `placeholder` olarak işaretle ve dosyanın başına "DOĞRULANMALI" listesine ekle.
   - Arayüz `placeholder` veya `extrapolated` veri kullanan her sonuçta görünür bir uyarı göstermeli.
2. **Birimler:** Hesap motorunun içi SI birimlerinde çalışır (m, K, Pa). Giriş ve çıkışta mm/inç ve °C/K desteklenir. Birim dönüşümleri için `pint` kullan. Fonksiyon imzalarında birimi isimde belirt (`depth_mm` gibi) ya da pint Quantity kullan, ikisini karıştırma.
3. **Hesap motoru arayüzden tamamen ayrı.** `core/` içinde saf fonksiyonlar olacak, Streamlit'e bağımlılık olmayacak, hepsinin `pytest` testi olacak.
4. **Sabit CTE kullanılmayacak.** Termal genleşme, 293.15 K referanslı integre ΔL/L tablosundan interpolasyonla hesaplanır.
5. Kod, değişken adları ve yorumlar İngilizce olacak. Arayüz metinleri Türkçe olacak (ileride çeviri yapılabilecek şekilde metinleri tek bir sözlükte tut).
6. Mühendislik varsayımlarını kodda açıkça belirt. Basitleştirme yaptığın her yere (deforme kesit şekli, kesit incelmesi formülü gibi) bir docstring notu yaz.

## 3. Teknoloji

- Python 3.11+, `pyproject.toml`, `uv` veya `pip` ile kurulum.
- Kütüphaneler: `numpy`, `scipy` (interpolasyon), `pint`, `pydantic` v2 (veri modeli ve doğrulama), `pyyaml`, `pandas` (standart ölçü tabloları), `plotly` (grafikler), `matplotlib` (yalnızca rapor ve statik çizim gerekirse), `streamlit` (arayüz), `pytest`.
- İleride eklenecekler: `ezdxf` (DXF çıktısı), rapor için `weasyprint` veya `reportlab`.

## 4. Dizin yapısı

```
oring_designer/
  data/
    seal_materials.yaml      # sızdırmazlık malzemeleri
    housing_materials.yaml   # gövde metalleri
    fluids.yaml              # akışkanlar + uyumluluk matrisi (uyarı amaçlı)
    design_rules.yaml        # squeeze/fill/stretch limitleri (yapılandırılabilir)
    extrusion_limits.yaml    # sertlik-basınç-boşluk tablosu
    standards/
      as568.csv
      iso3601_1.csv
  src/oring_designer/
    models.py        # pydantic modelleri
    loader.py        # YAML/CSV okuma ve doğrulama
    thermal.py       # eps_th(material, T), scale_dimension(...)
    geometry.py      # squeeze, stretch, fill, kesit incelmesi, eksantriklik
    gland_types.py   # piston, rod, face (iç basınç / dış basınç)
    checks.py        # kurallar -> PASS / WARN / FAIL + açıklama
    sweep.py         # sıcaklık taraması (conta ve gövde sıcaklığı ayrı)
    tolerance.py     # worst-case, RSS, Monte Carlo
    selector.py      # standart ölçü öneri motoru
    viz/
      section.py     # kesit çizimi
      plots.py       # sıcaklığa göre grafikler, MC histogramı
  app/
    streamlit_app.py
    pages/
  tests/
```

## 5. Veri modeli

### seal_materials.yaml (her malzeme için)
- `id`, `name`, `group`: `elastomer` | `thermoplastic`
- `hardness_shore_a` (elastomerler için aralık), PTFE ve PCTFE için `hardness_shore_d`
- `low_temp_limit_K`: Tg veya TR-10 değeri. Bunun altında elastomer sızdırmazlığı geçersiz sayılır.
- `high_temp_limit_K`
- `thermal_strain`: `[[T_K, dL_L], ...]` tablosu. dL/L değeri 293.15 K'de 0 olacak. Tablo mümkünse 20 K'e kadar inmeli. Elastomer verisi Tg'nin altında yoksa tabloyu orada bitir ve `extrapolated` olarak işaretle.
- `phase_transition_notes`: PTFE için yaklaşık 19 °C'deki kristal geçiş. Tablo bu geçişi içerecek kadar sık noktalı olmalı (283–313 K arasında 1 K adım; ~292 K ve ~303 K'deki iki geçişi de kapsar, bkz. §13 K6).
- `volume_swell`: akışkan bazında, opsiyonel.
- `source`, `data_quality`, `notes`

### housing_materials.yaml
- `id`, `name`, `thermal_strain` tablosu (4/20 K → 400 K), `source`, `data_quality`
- `cryo_toughness_warning`: bool ve not. 17-4 PH ve 15-5 PH gibi martenzitik PH çelikler kriyojenik sıcaklıkta tokluk kaybeder. Bu alaşımlar seçildiğinde ve sıcaklık belirli bir eşiğin altına indiğinde arayüz uyarı versin. Eşik değeri veriyle birlikte kaynaklı olarak tanımlanacak, kendin bir değer uydurma.
- Kaynak önerisi: NIST Cryogenic Material Properties veri tabanı ve Ekin, "Experimental Techniques for Low-Temperature Measurements" (integre büzülme tabloları). 1000 serisi için 1100, 3000 serisi için 3003 temsilci alaşım olarak alınır.

### fluids.yaml
- LOX, LN2, LH2, LCH4, GHe. Opsiyonel olarak depolanabilir itkiler: MMH, N2H4, NTO, RP-1.
- Her akışkan için `boiling_point_K` ve malzeme bazında uyumluluk: `ok` | `conditional` | `not_ok` | `unknown`. Varsayılan değer `unknown`. Bu matrisi kullanıcı dolduracak. Sadece çok iyi bilinen durumları kaynakla birlikte doldur (örneğin NBR/EPDM–LOX uyumsuzluğu).

### design_rules.yaml (varsayılanlar, kullanıcı değiştirebilir)
- Malzeme grubuna ve yuva tipine göre (`static_radial`, `static_face`, `dynamic_reciprocating`) şunlar: `squeeze_min`, `squeeze_max`, `fill_max`, `stretch_min`, `stretch_max`, rod tipi yuvalar için `circumferential_compression_max`.
- Elastomer için başlangıç değerlerini Parker O-Ring Handbook (ORD 5700) genel tavsiyelerinden al ve kaynağını yaz.
- Termoplastikler (PTFE/PCTFE) için ayrı bir kural seti olacak:
  - Gerdirerek montaj yapılamaz, bu yüzden "split/açılabilir yuva gerekir" uyarısı verilsin.
  - Sünme (cold flow) uyarısı verilsin.
  - "Yaylı conta (spring-energized) önerilir" notu eklensin.

## 6. Hesaplar

Tüm boyutlar referans sıcaklıkta (`T_ref`, varsayılan 293.15 K, kullanıcı değiştirebilir) verilir. **Conta sıcaklığı `T_seal` ve gövde sıcaklığı `T_housing` ayrı girdilerdir.** Soğuma geçişinde bu ikisi farklı olabilir.

1. **Termal ölçekleme:** `L(T) = L_ref * (1 + eps(T)) / (1 + eps(T_ref))`. Burada `eps` değeri tablodan, 293.15 K referanslı olarak alınır. (Düzeltildi, bkz. §13 K1 — önceki formül T = T_ref'te 1 vermiyordu.)
2. **Gerdirme (stretch):** `(groove_ID - oring_ID) / oring_ID`. Piston tipinde yuva tabanı çapı kullanılır. Rod tipinde ise o-ring dış çapının sıkışması hesaplanır.
3. **Gerdirmeye bağlı kesit incelmesi:** İki yöntem olacak ve seçilebilir:
   - Hacim korunumu: `CS' = CS / sqrt(1 + stretch)`
   - Parker handbook'taki ampirik ilişki
4. **Sıkıştırma (squeeze):** `(CS_eff - gland_depth) / CS_eff`
   - Radyal yuvalarda gland derinliği = yuva tabanı ile karşı yüzey arasındaki radyal mesafe. Diametral boşluk ve eksantriklik dikkate alınır: en kötü tarafta boşluk tamamen bir tarafa toplanır.
   - Face tipinde gland derinliği = yuva derinliği.
5. **Yuva doluluğu (gland fill):** `A_oring * (1 + swell) / A_groove`. Kesit alanı `A_oring = π CS_eff² / 4`. Yuva kesiti dikdörtgen kabul edilir, köşe radyüsleri opsiyonel olarak düşülür.
6. **Ekstrüzyon kontrolü:** Basınç, sertlik ve en kötü durumdaki diametral boşluk `extrusion_limits.yaml` tablosuyla karşılaştırılır. Limit aşılırsa destek halkası (backup ring) önerilir.
7. **Face tipinde basınç yönü:** İç basınçta o-ring yuvanın dış çapına oturacak şekilde yuva dış çapı ile o-ring dış çapı ilişkisi kontrol edilir. Dış basınçta iç çapa oturma kontrol edilir.
8. **Sıcaklık sınırı:** `T_seal < low_temp_limit_K` ise sonuç kesin FAIL olur ve "elastomer camsı bölgede" açıklaması verilir. Squeeze değeri uygun görünse bile sonuç FAIL kalır.
9. Her kontrol `CheckResult(status, value, limit, message_tr)` döndürür.

## 7. Sıcaklık taraması ve tolerans

- `sweep.py`: Kullanıcının verdiği aralıkta (örneğin 20 K – 350 K) squeeze, fill, stretch ve boşluk değerlerini hesaplar.
- İki mod olacak:
  - `T_seal = T_housing` (denge durumu)
  - Gecikme senaryosu: `T_seal = T_housing + ΔT` (pozitif ve negatif ΔT)
- `tolerance.py`:
  - Worst-case: tüm tolerans köşe kombinasyonları denenir.
  - RSS
  - Monte Carlo: varsayılan N = 20.000. Toleranslar ±3σ normal dağılım ya da uniform olarak seçilebilir. Seed sabitlenebilir olmalı.
  - Çıktı: her kontrol için geçme oranı (%) ve dağılım verisi.

## 8. Standart ölçü önerisi

- `as568.csv` sütunları: `dash`, `id_in`, `id_tol_in`, `cs_in`, `cs_tol_in`. `iso3601_1.csv` için de karşılığı.
- Standart tabloları telifli. AS568 değerlerini bilinen genel yayınlardan (örneğin Parker handbook tabloları) doldurabilirsin, ama CSV başına "standarda karşı doğrulanmalı" notu ekle ve `data_quality` sütunu koy.
- `selector.py`:
  - Kullanıcı yuva tipini, nominal çapı (bore veya rod), malzemeyi, basıncı, sıcaklık aralığını ve tercih edilen kesit aralığını girer.
  - Motor tüm standart o-ringleri tarar ve her biri için tüm sıcaklık aralığında ve tolerans uçlarında yuva boyutlarını önerir/hesaplar.
  - Sonuçları puanlayıp sıralar. Puanlama kriteri: hedef squeeze'e yakınlık, fill marjı, stretch.
  - Önerilen yuva boyutları (derinlik, genişlik, çap) toleranslarıyla birlikte verilir.

## 9. Görselleştirme

- **Kesit çizimi (`section.py`):** Yuva ve karşı yüzey gerçek ölçekte çizilir. O-ring serbest haliyle (daire) ve sıkışmış haliyle gösterilir. Sıkışmış şekil, alanı koruyan yuvarlatılmış dikdörtgen/elips yaklaşımıyla çizilir ve bunun yaklaşım olduğu belirtilir. Üç durum üst üste ya da yan yana gösterilir: `T_min`, `T_ref`, `T_max`. Ölçü okları ve squeeze/fill etiketleri olacak.
- **Grafikler (`plots.py`, plotly):**
  - Sıcaklığa göre squeeze (%) ve fill (%). İzin verilen bantlar gölgeli, Tg çizgisi dikey kesikli çizgi olarak.
  - Sıcaklığa göre radyal boşluk.
  - Monte Carlo histogramları, limit çizgileriyle.
  - Malzeme karşılaştırması: seçilen conta ve gövde malzemelerinin ΔL/L(T) eğrileri.

## 10. Arayüz (Streamlit, Türkçe)

Sayfalar:
1. **Yuva Kontrol:** Mevcut bir tasarımı girip kontrol etme.
2. **Ölçü Öner:** Çap ve şartlardan standart o-ring ve yuva önerisi.
3. **Malzeme Verileri:** Tabloların ve ΔL/L eğrilerinin görüntülenmesi, `data_quality` rozetleriyle.
4. **Tolerans Analizi**

Genel arayüz kuralları:
- Sol panelde birim seçimi (mm/inç, °C/K) olacak.
- Sonuçlar PASS / WARN / FAIL renk kodlu bir tabloda gösterilir. Her satırda açıklama bulunur.
- Placeholder veri kullanılıyorsa sayfanın üstünde sarı bir uyarı bandı çıkar.
- Ağır hesaplarda `st.cache_data` kullanılır.

## 11. Fazlar ve kabul kriterleri

Her fazın sonunda testler geçmeli, kısa bir özet yazılmalı ve kullanıcı onayı beklenmeli.

- **Faz 0 – İskelet:** pyproject, dizin yapısı, boş modüller, pytest çalışıyor, "merhaba" diyen Streamlit sayfası açılıyor.
- **Faz 1 – Veri ve termal:** pydantic modelleri, YAML dosyaları (kaynak ve kalite alanlarıyla), `thermal.py`. Testler:
  - 293.15 K'de ölçek = 1
  - Tablolar monoton
  - PTFE geçiş bölgesi doğru interpolasyonla geçiliyor
  - Tablo aralığı dışına çıkan sıcaklıkta açık bir hata veriliyor
  - "DOĞRULANMALI" listesinin çıktısı alınıyor
- **Faz 2 – Tek sıcaklıkta geometri:** Piston, rod ve face (iç/dış basınç) hesapları ve kontroller. Testler: elle hesaplanmış en az 3 örnek. Parker handbook tasarım örneğiyle karşılaştırma yapılır.
- **Faz 3 – Sıcaklık taraması ve ilk arayüz:** `sweep.py`, ayrı conta ve gövde sıcaklığı, Tg kontrolü. "Yuva Kontrol" sayfası ve squeeze/fill–sıcaklık grafiği.
- **Faz 4 – Tolerans analizi:** Worst-case, RSS ve Monte Carlo, histogramlar.
- **Faz 5 – Standart ölçü önerisi:** AS568 ve ISO 3601 tabloları, `selector.py`, "Ölçü Öner" sayfası.
- **Faz 6 – Kesit görselleştirmesi:** Üç sıcaklık durumu, ölçülendirme.
- **Faz 7 – Kriyojenik termoplastik ve yaylı conta modu:** PTFE/PCTFE kural seti. Yaylı conta için üretici katalog yuva ölçüleri kullanıcı tarafından girilir, program termal boşluk ve sıkışma kontrolünü yapar.
- **Faz 8 – Çıktılar:** PDF/Markdown tasarım raporu (girdiler, sonuçlar, grafikler, kullanılan verilerin kaynakları), DXF yuva profili.

## 12. Çalışma şekli

- Faz 0'a başlamadan önce bu dokümandaki belirsizlikleri ve önerdiğin değişiklikleri listele, onay al.
- Hesap formüllerini yazmadan önce her birini docstring'de kaynağıyla birlikte belirt.
- Malzeme verilerinden emin olmadığın bir değer varsa tahmin etme. `placeholder` olarak bırak ve bana sor.
- Küçük ve okunabilir commit'ler yap. Her faz ayrı bir branch ya da commit grubu olsun.

## 13. Kararlar ve spec değişiklikleri (2026-11-13, Faz 0 öncesi)

Bu bölüm yukarıdaki maddelerle çelişirse bu bölüm geçerlidir.

- **K1 – Termal ölçekleme:** `L(T) = L_ref · (1 + ε(T)) / (1 + ε(T_ref))` (kesin ifade). Test: T_ref ≠ 293.15 K için de `scale(T_ref) = 1`.
- **K2 – Tablo dışı sıcaklık:** `thermal.py` tablo dışında açık hata verir. `sweep.py` bu hatayı yakalar ve o noktaları "veri yok" olarak işaretler. Ekstrapolasyon yalnızca açık `allow_extrapolation=True` ile yapılır ve sonuç `extrapolated` olarak işaretlenir.
- **K3 – Elastomer termal verisi:** Kaynaklı ΔL/L tablosu yoksa tablo **boş bırakılır** (seçenek a). Sabit α'dan türetilmiş tablo üretilmez. Sonuç: tablo eklenene kadar bu malzeme için ölçekleme yalnızca `T = T_ref`'te yapılabilir.
- **K4 – Düşük sıcaklık sınırı:** `tg_K` ve `tr10_K` ayrı alanlardır. `T_seal < Tg` ise FAIL, `Tg ≤ T_seal < TR-10` ise WARN. Elastomerler şimdilik polimer ailesi seviyesinde tutulur. Veri modeli opsiyonel bir `grade` alanı ile compound/grade eklemeye açıktır. Elastomerler pratikte kriyojenik olmayan sıcaklıklarda kullanılacaktır.
- **K5 – Karşı parça (iki parçalı gövde):** Varsayılan olarak tek gövde malzemesi ve tek `T_housing` kullanılır. Kullanıcı arayüzde bir seçenek işaretlerse karşı parça (`mating_part`) için ayrı malzeme ve ayrı sıcaklık girebilir.
- **K6 – PTFE:** ~292 K ve ~303 K'deki iki geçiş için 283–313 K arasında 1 K adımlı tablo kullanılır. Varsayılan kayıt virgin PTFE'dir. Dolgulu tipler (cam, karbon, bronz) ayrı kayıt olarak eklenebilir.
- **K7 – Isıl işlem durumu:** Gövde malzemeleri seçilebilir ısıl işlem / temper durumlarına sahiptir (örn. 17-4 PH H900/H1025/H1150, 17-7 PH TH1050/RH950, Al -T6). Tokluk uyarısı ve kaynağı duruma bağlıdır. Termal tablo, durumlar arasında fark için kaynak yoksa alaşım seviyesinde paylaşılır.
- **K8 – 17-7 PH:** Kullanıcının "17-5 PH" ifadesi 17-7 PH olarak kabul edildi (`notes` alanına yazılacak).
- **K9 – Parker referansı:** Dünyada en yaygın kullanılan genel referans olan Parker O-Ring Handbook ORD 5700'ün güncel yayımlanmış baskısı kullanılır. Baskı/yıl ve sayfa numarası her `source` alanına yazılır. Ampirik kesit incelmesi katsayıları hafızadan değil, bu baskıdan alınır.
- **K10 – Birimler:** Çekirdekte numpy ile SI cinsinden düz float kullanılır, isimlerde `_m`, `_K`, `_Pa` sonekleri bulunur. pint yalnızca giriş/çıkış katmanında (`units.py`) kullanılır. Arayüz birimleri: uzunlukta mm/inç, sıcaklıkta °C/K/°F, basınçta bar/MPa/psi.
- **K11 – Mesajlar ve dil:** Çekirdek Türkçe metin üretmez. `CheckResult` içinde `status`, `value`, `limit`, `code` ve `params` alanları bulunur. Türkçe metin `i18n/tr.yaml` sözlüğünden üretilir.
- **K12 – data_quality:** `measured_reference`, `literature`, `vendor`, `user_measured`, `extrapolated`, `placeholder`. `source` alanı `data/references.yaml` içindeki bir `ref_id`'ye işaret eder.
- **K13 – İnterpolasyon:** PCHIP (monoton koruyan) kullanılır. Monotonluk testi "azalmayan" şeklindedir.
- **K14 – Stretch ve kesit incelmesi:** Raporlanan stretch ID bazlıdır (Parker konvansiyonu). Hacim korunumu ile kesit incelmesi hesabında merkez çap gerinimi kullanılır.
- **K15 – Eksantriklik:** `eccentricity` girdisinin varsayılanı tam eksantrikliktir. Squeeze hem dar hem geniş tarafta kontrol edilir.
- **K16 – Hidrojen:** Gövde malzemesine `hydrogen_embrittlement_warning` alanı eklenir (aday kaynak: Sandia, *Technical Reference for Hydrogen Compatibility of Materials*). LOX uyumluluğu için aday kaynaklar NASA-STD-6001 ve ASTM G63/G94.
- **K17 – ISO 3601-1:** Kapsam ve sınıflar Faz 5'te kaynağa karşı doğrulanacak. Varsayılan olarak her iki seri de yüklenir.
- **K18 – Veri dizini:** `data/` repo kökündedir. Loader dosya yolunu parametre olarak ya da `ORING_DESIGNER_DATA` ortam değişkeninden alır.
- **K19 – `dynamic_reciprocating`:** YAML'da yer tutucu olarak bulunur. İmplementasyon sonraki bir faza bırakılmıştır.

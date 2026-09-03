# Ergene Mikrokirletici Ontolojisi → Q2 Makale Planı

> **REVİZYON (2026-08-03, ilk uygulama oturumu).** Kullanıcı `Data/` altına shapefile'lar, 4 mevsimlik
> kampanya ve mevcut Python DSS kodunu ekledi. Bu, aşağıdaki planın dayandığı varsayımların çoğunu
> **yukarı yönlü** değiştirdi. Değişenler → [Revize edilmiş temel](#revize-edilmiş-temel-2026-08-03) bölümü.
> Aşağıdaki orijinal Context tarihsel kayıt olarak duruyor.

## Context

2018 İTÜ bitirme projesi (`ProjectOwl_v3.owl` + powerdot sunum) yayımlanabilir bir dergi makalesine
dönüştürülecek. Mevcut durum tespiti:

**Elimizdeki gerçek varlık — `Data/` klasörü (asıl değer burada):**
| Dosya | İçerik | Satır |
|---|---|---|
| `ResourceOfPollutants.xlsx` | Ergene 2017-11 kampanyası: 82 kirletici × 19 istasyon | 802 ölçüm |
| `Toxicity_Ecosar_FINAL-2018_03_12.xlsx` | ECOSAR QSAR: 222 kimyasal × Fish/Daphnid/Algae × LC50/EC50/ChV, 42 yapısal sınıf | 1332 |
| `CKS_FEnCY.xlsx` | ÇKS (YO + MAK), nehir/göl — EU-WFD EQS'in TR karşılığı | 153 |
| `CKS_FEnCY-2.xlsx` | LOD/LOQ/Slope/R² (79) + LC-MS/MS sMRM geçişleri (157) | 4 sayfa |
| `Properties_report order_2018-07-04.xlsx` | SMILES, LogP, çözünürlük, MW, exact mass, Henry sabiti | 223 + 18 metal |
| `75GözlemNokDeşarjNok.xlsx` | gözlem noktası → deşarj noktası eşlemesi | 75 |

**Ontolojinin (v3) durumu — hakem gözüyle reddedilme sebepleri:**
- IRI: `http://www.semanticweb.org/recep/ontologies/2018/0/untitled-ontology-15` (Protégé default, kullanıcı adı içeriyor, dereferans edilemez, versionIRI/lisans/creator yok → FAIR F1/F2/A1/R1.1 fail)
- **0 `rdfs:label`, 0 `rdfs:comment`** (174 entity) → OOPS! P08 critical
- **0 disjointness, 0 equivalentClass, 0 inverseOf, 0 SWRL** → reasoner hiçbir şey çıkarsamıyor;
  tutarlılık "başarı" değil, çelişki üretebilecek konstrüktör hiç yok
- **0 `owl:imports`** — SOSA/SSN, GeoSPARQL, OM/QUDT, ChEBI sıfırdan (ve hatalı) yeniden yazılmış
- `latitude`/`longitude`/`altitude` = **`xsd:string`** → "GIS-based" başlığı karşılanmıyor
- Sessiz yanlış çıkarımlar: `'Ergene_River'` → `RiverSegment` olarak sınıflanır; `Arsenic/Barium/Beryllium`
  → `UnitOfMeasure` olarak sınıflanır (disjointness olmadığı için çelişki vermiyor, sadece yanlış)
- Bozuk IRI'ler: `#1`–`#5` (rakamla başlıyor), `#'Ergene_River'` (tırnak karakteri IRI içinde)
- Yazım hataları IRI'ye gömülü: `Compund`, `Theoritical`, `Organometalic`
- 92 sınıfın **87'sinde hiç birey yok**; 802 ölçüm hiç RDF'e çevrilmemiş (sunumda "future work")
- Sunumdaki 2834 aksiyom / 71 sınıf / 437 birey rakamları **v4**'e ait — **v4 dosyası klasörde yok**,
  sadece `ProjectOwl_v4.svg` / `.png` render'ı var

**Hedeflenen sonuç:** 2–3 ayda, Q2 seviyesinde, tek ve net bir metodolojik katkısı olan makale.

---

## Revize edilmiş temel (2026-08-03)

### 1. Gerçek ontoloji v3 değil — `TheOntologyGISDSS.owl`
`Data/Sampling/app_framework.py:10` şu IRI'yi yüklüyor:
`http://web.itu.edu.tr/altinbagr/ontology/TheOntologyGISDSS.owl` → **indirildi** (393 KB, repo köküne).

| Metrik | v3 | **TheOntologyGISDSS** | Sunumdaki iddia |
|---|---|---|---|
| Sınıf | 92 | **72** | 71 |
| Object property | 21 | **26** | 25 |
| Datatype property | 8 | **23** | 20 |
| Annotation property | 0 | **2** | 4 |
| Birey | 53 | **444** | 437 |
| `rdfs:label` | 0 | **363** | — |
| `rdfs:comment` | 0 | **34** | — |
| disjoint / equiv / inverse / imports / SWRL | 0 | **0** | — |

→ **Baseline bu dosya olacak, v3 değil.** Label/comment sorunu büyük ölçüde çözülmüş.
Ama disjointness, inverse, import, kural katmanı hâlâ sıfır → WP3/WP5 aynen geçerli.
Ek olarak bu sürümde `maxEQS`/`averageEQS`, `Toxicity` (EC50-5/EC50-15), `PollutantDomain`,
`Micro`/`Conventional`/`Metal`, `WaterFlowSecond`, `hasNumericalValue`, ve **koordinatlı**
`SingularIndustrial`/`OrganizedIndustrial` bireyleri var.
*(IRI hâlâ `untitled-ontology-15` — kimlik/FAIR sorunu devam ediyor.)*

### 2. Tek kampanya değil — 4 mevsim
`Data/Sampling/Sampling/{February,May,August,November}_Sampling-2018_*.xlsx`
→ "tek kampanya" limitasyonu **düşüyor**; mevsimsel analiz (debi-konsantrasyon ilişkisi,
kuru/ıslak dönem EQS aşımı) yeni bir sonuç ekseni açıyor.

### 3. Tam GIS yığını mevcut (`Data/ShapeFiles/`)
| Katman | Dosya | Ontolojideki karşılığı |
|---|---|---|
| Nehir ağı (from/to node + Strahler) | `Erg_river/Erg_river_Hydro.shp` | `RiverSegment`, `Node`, `treeLevel` |
| Ana nehir | `Erg_river/Erg_mainriver_Hydro.shp` | `River` |
| Nehir v2 | `nehir_v2/Erg_river_GE.shp` | — |
| **OSB firmaları + planları** | `osbler/OSBFirmalar.shp`, `OSBPlanlar.shp` | `OrganizedIndustrial`, `Industry` |
| **Tarım alanları** (sulama + yeraltısuyu) | `tarimalanlari/TarimAlanlari-*.shp` | `AreaSources → Agricultural` |
| **Kentsel alan** (Corine CLC12) | `urban/g100_clc12_v18_5_Ergene_UrbanCity.shp` | `PointSources → Domestic` |
| İdari sınırlar (il/ilçe/köy) | `idari-sinirlar/*.shp` | bağlamsal |

→ Ontolojinin `PointSources`/`AreaSources` taksonomisinin **gerçek geometrik karşılığı var**.
"GIS-based" iddiası artık tamamen savunulabilir; **ISPRS IJGI hedef listesine güçlü şekilde giriyor**.

### 4. Çalışan bir DSS motoru zaten var (1739 satır Python)
| Dosya | Satır | İçerik |
|---|---|---|
| `tree_algorithm.py` | 844 | Segment ağacı (Strahler), konsantrasyon/debi/**kütle yükü** farkı yayılımı, `flow_correction`, `truncatingTree`, BFS/preorder/postorder gezinme, `advice`/`warning` üretimi |
| `designv0.py` | 680 | PyQt5 GUI, `IndustryPlot`, `PollutantContrabition`, `PollutantAndResource` |
| `app_framework.py` | 189 | owlready2 ontoloji erişim katmanı, `ControlPollutantConcVSeQS` |
| `QueryWithShp.py` | 26 | shapefile ↔ gözlem noktası eşleme |

**Kütle yükü (load = konsantrasyon × debi) farkı ile kaynak atfı**, planda öngördüğümüz
"indicator compound" kuralından **daha güçlü** bir yöntem: iki ardışık segment arasındaki yük artışı
aradaki deşarjı nicel olarak işaret eder. Bunu SWRL/SPARQL'e taşımak makalenin omurgası olmalı.

### 5. Özgünlük iddiası kodda zaten doğrulanıyor
`app_framework.py:131-143` `ControlPollutantConcVSeQS`: `> maxEQS` → kırmızı, `> averageEQS` → sarı,
altı → yeşil, **EQS'i olmayan kirletici → gri `#808780`**.
Yani "karar verilemeyen" durum kodda zaten var ama **gayri resmî, gerekçesiz ve rapor edilmiyor**.
Makalenin katkısı tam olarak bu gri kutuyu formalize etmek: EQS yokluğu + LOQ > EQS + LOD altı
durumlarını ayrı ayrı, mantıksal olarak tanımlanmış sınıflara ayırmak.

### 6. Hedef dergi revizyonu
Bu varlıklarla makale Q1 denemesini hak ediyor:
`Ecological Informatics` (Q1) veya `Environmental Modelling & Software` (Q1) → düşerse
`ISPRS IJGI` / `Water` (Q2). Q2 zaten güvenli bölgede.

### 7. Yeni iş paketi — WP-R: Yeniden üretilebilirlik (tüm WP'lere paralel)
Mevcut kodun hakem gözüyle sorunları: `os.getcwd()`'ye bağlı yollar, analiz mantığı PyQt5 GUI'ye
gömülü, ortam pinlenmemiş, ontoloji dosyası uzak sunucudan yükleniyor (kaybolursa iş biter),
Python 3.8, rastgelelik/sıralama determinizmi denetlenmemiş.
Yapılacaklar:
- Analiz mantığını GUI'den ayır → saf fonksiyon kütüphanesi + ince CLI; GUI opsiyonel
- `environment.yml` + `requirements.txt` **pinli sürümlerle**; `rdflib`, `owlready2`, `pyshacl`,
  `geopandas`, `pyshp` kurulacak (şu an yok — mevcut ortam Python 3.8.8)
- Tüm yollar repo köküne göreli; `os.getcwd()` kullanımı kaldırılacak
- Ontoloji ve tüm girdiler repoya vendor'lanacak (uzak IRI'ye çalışma zamanı bağımlılığı olmayacak)
- `make all` / `snakemake` ile tek komutla ham veri → şekil/tablo üretimi
- Her figür ve tablo bir script tarafından üretilecek, elle düzenleme olmayacak
- Sabit random seed; deterministik sıralama (dict/set iterasyonu sıralanacak)
- Zenodo DOI + GitHub tag; `CITATION.cff`; ODC-BY (veri) + CC BY 4.0 (ontoloji) + MIT (kod)
- Smoke test: temiz ortamda `make all` → makaledeki sayıları birebir yeniden üretir

---

## Özgün katkı (makalenin tek cümlelik iddiası)

> Mevcut su kalitesi ontolojileri (WaWO+, OPO, SAREF4WATR, Water Health KG) ölçümü **kesin bir sayı**
> varsayar. Mikrokirleticilerde ölçümlerin büyük kısmı LOD/LOQ altındadır ve **LOQ altı bir değeri EQS
> ile kıyaslamak analitik olarak geçersizdir** — ama pratikte rutin olarak yapılır. Bu çalışma,
> **analitik geçerliliği (LOD/LOQ), regülasyon eşiğini (ÇKS/EQS) ve tahmini ekotoksisiteyi (ECOSAR PNEC)
> aynı mantıksal katmanda birleştiren, sansürlü veriye duyarlı (censoring-aware) bir OWL 2 DL modeli ve
> kural katmanı** önerir; Ergene Havzası'nda 802 ölçüm üzerinde doğrular.

Reasoner'ın gerçekten yaptığı üç iş (makalenin omurgası):

**1. Sansürlü veri semantiği — literatürdeki asıl boşluk**
```
CensoredObservation    ≡ Observation ⊓ ∃hasValue.[< LOD-of-its-analyte]
EstimatedObservation   ≡ Observation ⊓ ∃hasValue.[LOD ≤ x < LOQ]
QuantifiedObservation  ≡ Observation ⊓ ∃hasValue.[≥ LOQ]
EQSExceedance          ≡ QuantifiedObservation ⊓ ∃exceeds.EQSThreshold
IndeterminateCompliance ≡ Observation ⊓ ¬QuantifiedObservation ⊓ ∃hasAnalyte.(∃hasEQS.Threshold ⊓ [LOQ > EQS])
```
Son satır kritik: **LOQ > EQS olan analitler için uyum kararı verilemez.** Bu, veride gerçekten var olan
ve rapor edilmeyen bir durum. Ontolojinin bunu *açıkça işaretlemesi* makalenin en güçlü tarafı.

**2. Risk kademelendirme (ECOSAR → PNEC → RQ)**
`PNEC = min(ChV_fish, ChV_daphnid, ChV_algae) / AF`, `RQ = MEC / PNEC`
→ tanımlı sınıflar: `NegligibleRisk` (RQ<0.01), `LowRisk` (0.01–0.1), `ModerateRisk` (0.1–1), `HighRisk` (≥1)

**3. Topoloji-duyarlı kaynak atfı (SWRL)**
- `locatedIn` transitive + `upstreamOf` transitive kapanış → yukarı havza deşarj adayları
- **Indicator compound kuralı** — veride hazır: `Special to Resource` bloğu (Atrazin→63,
  α-Terpineol→64, 4-MBC→9, Tebukonazol→71). Tek noktada görülen bileşik → o deşarjın parmak izi.
```
Observation(?o) ∧ hasAnalyte(?o,?a) ∧ IndicatorCompound(?a) ∧ QuantifiedObservation(?o)
  ∧ atPoint(?o,?p) ∧ upstreamDischarge(?p,?d) ∧ characteristicOf(?a,?d)
  → attributedTo(?o,?d)
```

Bu üçü kısa, birbirine bağlı ve **mevcut veriyle tamamen desteklenebilir**. Yeni veri toplama gerekmez.

---

## Hedef dergi merdiveni

| Sıra | Dergi | Q / IF (yaklaşık) | Uyum | Not |
|---|---|---|---|---|
| 1 | **Ecological Informatics** (Elsevier) | Q1, ~7.3 | Çok iyi | Hızlı desk-reject riski var ama denemeye değer; reddi hızlı gelir |
| 2 | **Water** (MDPI) | **Q2, ~3.5** | Çok iyi | **Ana hedef.** İlgili Special Issue ara. APC ~2600 CHF |
| 3 | **Environmental Monitoring and Assessment** (Springer) | Q2, ~3.0 | Çok iyi | **APC yok** (abonelik seçeneği). Ergene vaka çalışması için ideal |
| 4 | **ISPRS Int. J. Geo-Information** (MDPI) | Q2 | İyi | Sadece GIS/geospatial tarafını güçlendirirsek |
| 5 | **Journal of Hydroinformatics** (IWA) | Q2/Q3, ~2.5 | İyi | Güvenli liman |
| — | Semantic Web Journal | Q2, ~2.9 | Orta | Ontoloji mühendisliği titizliği çok yüksek istenir; ancak ontoloji gerçekten FAIR yayımlanırsa |

**Strateji:** Ecological Informatics → (red) → Water veya EM&A. Q2 hedefi gerçekçi ve ulaşılabilir.
Makaleyi baştan **Water** formatında yazıp Ecological Informatics'e uyarlamak en verimlisi.

---

## Yapılacaklar (10–12 hafta)

### WP0 — Ön koşullar (Hafta 1, BLOKE EDİCİ)
1. **Veri hakları ve yazarlık** *(karar: proje ekibiyle temasa geçilecek)*. `CKS_FEnCY`,
   `Toxicity_Ecosar`, `Properties_report`, 802 ölçüm bir projeden (muhtemelen TÜBİTAK/İTÜ Çevre Müh.)
   geliyor. PI onayı + eş yazarlık netleştirilecek; danışman Dr. Mehmet Tahir Sandıkkaya da eş yazar.
   **Bu netleşmeden submit edilemez.** İlk hafta halledilmezse WP1–WP7 yine ilerler (ontoloji ve
   metodoloji veriden bağımsız), sadece WP4 (ABox) ve WP9 (Zenodo veri yayını) bekler.
2. **İstasyon koordinatları** *(karar: bulunabilir)*. 19 (ideal: 75) istasyonun WGS84 koordinatı
   toplanacak → `data/raw/stations.csv` (`station_id, lat, lon, name, notes`).
   GIS çerçevesi ve Figure 4 (risk haritası) planda kalıyor. **Nehir ağı geometrisi (shapefile/GeoJSON)
   ayrıca bulunabilirse** gerçek hidrolojik upstream/downstream topolojisi kurulur ve IJGI de hedef
   listesine girer; bulunamazsa segment grafiği koordinat + `75GözlemNokDeşarjNok` eşlemesinden
   türetilir (bu durumda "topolojik yakınlık, hidrolik taşınım modeli değil" limitations'ta belirtilir).
3. **`ProjectOwl_v4.owl` dosyasını bul.** Sunumdaki rakamlar ona ait; `Toxicity`, `pH`, `WaterProperty`,
   `Hospital`, `Municipality` sınıfları sadece v4'te var. Eski disk/Protégé workspace/Overleaf'e bak.
   Bulunamazsa kayıp değil — bu sınıflar zaten `ripo-ecotox` ve `ripo-core` modüllerinde sıfırdan
   ve daha temiz kurulacak.

### WP1 — Literatür ve boşluk analizi (Hafta 1–2)
- 60–80 referans; Zotero/BibTeX (`refs.bib`)
- Zorunlu okuma/atıf kümesi:
  - Ontoloji standartları: SOSA/SSN (Janowicz et al.), GeoSPARQL, QUDT/OM (Rijgersberg), SKOS, PROV-O, ChEBI
  - Su ontolojileri: WaWO+ (EM&S 2016), OPO (Water 2020, 10.3390/w12030715), Ahmedi & Jajaga
    (CEUR Vol-1063), SAREF4WATR, Water Health Open KG (Sci Data 2025)
  - Metodoloji: LOT (Poveda-Villalón, EAAI 2022), NeOn, OOPS! (IJSWIS 2014), FOOPS!
  - Alan: ECOSAR/QSAR, EU-WFD EQS, Ergene havzası kirlilik literatürü (TR), censored data in
    environmental monitoring (substitution vs. ROS/MLE — Helsel)
- **Çıktı: karşılaştırma tablosu** (Table 1) — satır: mevcut ontolojiler, sütun: standart reuse /
  spatial topology / analytical provenance (LOD-LOQ) / regulatory thresholds / ecotoxicity /
  rule layer / public ABox. Bizim satırımız tek dolu olan sütunları gösterir. Bu tablo makalenin
  novelty argümanının kanıtıdır.

### WP2 — Yetkinlik soruları (Hafta 2)
20–25 competency question yaz, her birini bir SPARQL sorgusuna ve en az bir aksiyoma bağla. Örnek:
- CQ1: Hangi istasyonlarda hangi analitler MAK-ÇKS'i geçiyor?
- CQ4: Hangi ölçümler LOQ altında olduğu için uyum değerlendirmesine alınamaz?
- CQ7: LOQ'su kendi EQS'inden büyük olan analitler hangileri? *(analitik metot yetersizliği)*
- CQ11: Bir gözlem noktasının yukarı havzasındaki deşarj noktaları hangileri?
- CQ14: RQ ≥ 1 olan ölçümlerin bileşik sınıfı (ECOSAR class) dağılımı nedir?
- CQ19: Tek bir noktaya özgü (indicator) bileşikler ve işaret ettiği deşarj?

### WP3 — Ontoloji v5: modüler yeniden inşa (Hafta 2–4)
*(Karar: v3'ü yamamak yerine modüler yeniden inşa.)* LOT metodolojisiyle; v3 kavramsal referans olarak
kullanılır (sınıf listesi, restriction'lar), ancak dosya devralınmaz — yeni IRI, yeni serileştirme (Turtle),
standart ontolojiler üzerine kurulum. Bu, "üç W3C standardını yeniden yazmışsınız" eleştirisini kökten kaldırır.

**Kimlik ve metadata**
- IRI: `https://w3id.org/ripo/` (w3id.org kalıcı IRI servisi — ücretsiz, dereferans edilebilir)
  Ontoloji adı önerileri: **RIPO** (River Pollution Ontology) / **MPO** (Micropollutant Observation Ontology)
- `owl:versionIRI`, `owl:versionInfo "1.0.0"`, `dcterms:title/creator/contributor/description/license
  (CC BY 4.0)/created/modified`, `bibo:doi`, `vann:preferredNamespacePrefix`

**Modüller (ayrı dosyalar, `owl:imports` ile)**
| Modül | İçerik | Reuse edilen |
|---|---|---|
| `ripo-core.ttl` | analit, ölçüm, uyum, risk sınıfları | SOSA/SSN, PROV-O, SKOS |
| `ripo-space.ttl` | havza/alt havza/nehir/segment/node/istasyon | **GeoSPARQL** (`geo:asWKT`, `geo:sfWithin`), HY_Features hizalaması |
| `ripo-chem.ttl` | kimyasal özellikler, SMILES, LogP, CAS | **ChEBI/CHEMINF** `skos:exactMatch`, PubChem |
| `ripo-analytics.ttl` | LOD/LOQ/slope/R², LC-MS/MS MRM geçişleri | — (**burası gerçekten özgün**) |
| `ripo-regulatory.ttl` | ÇKS/EQS eşikleri (YO + MAK) | — |
| `ripo-ecotox.ttl` | ECOSAR sınıf, organizma, endpoint, PNEC | — |

**Zorunlu düzeltmeler (v3'ten devralınan hatalar)**
- Tüm birim/prefix modülünü sil → **QUDT** veya **OM 2** import et (35 el yapımı birey gider)
- `Observation`/`Observer`/`ObservationPoint` → `sosa:Observation` / `sosa:Sensor` / `sosa:FeatureOfInterest`
- `lat`/`lon`/`alt` → `xsd:double`, ayrıca `geo:asWKT` geometri
- Tüm 174+ entity'ye `rdfs:label`@en (+ opsiyonel @tr) ve `rdfs:comment` (özellikle LC-MS kısaltmaları:
  CE, CES, EPI, CXP, DP, EP, RT, Q1-Q3, LOD, LOQ)
- Disjointness ekle: `(River, RiverSegment)`, `(Point, Line, Polygon)`, `(Basin, Watershed, Catchment)`,
  `(Prefix, Quantity, UnitOfMeasure)` — **ekledikten sonra reasoner'ı tekrar çalıştır**, v3'teki iki
  sessiz hata artık gerçek inconsistency olarak çıkacak, düzelt
- `HeavyMetal ⊑ Metal`; `Industrial` kimyasal partisyondan çıkar; `Industry`'yi `PollutionSources`'a bağla
- `isPartOf` transitive yap; `has`/`isPartOf`, `contain`/`within` için `owl:inverseOf`; `from`/`to` functional
- `isA` property'sini sil (rdf:type anti-pattern)
- `numerator`/`denominator`/`prefix`'i `observation` altından çıkar (anlamsız gruplama)
- Attribute-as-class anti-pattern'i düzelt: `LogP`, `ExactMass`, `Solubility`, `SegmentLength`,
  `CatchmentArea` → datatype property veya QUDT `Quantity` pattern
- IRI'leri normalize et: `Node1..Node5`, `ErgeneRiver`; `Compund→Compound`, `Theoritical→Theoretical`,
  `Organometalic→Organometallic`; tekil isimlendirme; lowerCamelCase property

### WP4 — ABox üretim hattı (Hafta 4–5)
`scripts/build_kg.py` — `openpyxl` + `rdflib`:
- 6 xlsx → normalize CSV → RDF/Turtle
- `ResourceOfPollutants.xlsx` merged-cell yapısını forward-fill ile çöz (kirletici adı sadece ilk satırda)
- Kimyasal adlarını 5 dosya arasında eşleştir (fuzzy + manuel eşleme tablosu; CAS varsa CAS öncelikli)
- Beklenen ölçek: **~15–25k triple**, 802 `sosa:Observation`, 82 analit, 19–75 istasyon, 222 kimyasal
  × 9 ekotoks endpoint
- Çıktı: `ripo-ergene-abox.ttl` (+ Zenodo DOI ile yayımla)
- **Provenance**: her triple'a PROV-O ile kaynak dosya/kampanya atfı

### WP5 — Akıl yürütme katmanı (Hafta 5–6)
- Tanımlı sınıflar (yukarıdaki 1 ve 2 numaralı bloklar) — OWL 2 DL içinde kalacak şekilde;
  sayısal aralık karşılaştırmaları için `xsd` facet restriction'ları nerede yetiyor nerede yetmiyor
  **açıkça tartış** (bu bir metodolojik bulgu)
- **SWRL** kural seti (~12–18 kural): eşik aşımı, RQ hesabı, upstream kapanış, indicator atfı
- **SHACL** shape'leri: veri kalitesi kısıtları (her ölçümün birimi olmalı, her analitin LOD'u olmalı,
  değer negatif olamaz) — SWRL'in yapamadığı validasyon
- Reasoner: **HermiT** + **Pellet** (owlready2 üzerinden), materialization süreleri ölç
- Ölçeklenebilirlik: ABox'ı 1×/10×/100× sentetik çoğaltıp reasoning süresi grafiği (Figure)

### WP6 — Değerlendirme (Hafta 6–7)
Hakem bunu arayacak, eksiksiz olmalı:
1. **OOPS!** taraması → pitfall tablosu (v3 "before" vs v5 "after" karşılaştırması — güçlü bir figür)
2. **FOOPS!** FAIR skoru (before/after)
3. **CQ kapsama**: 25 CQ → 25 SPARQL → sonuç tablosu
4. **Reasoner**: tutarlılık, inferred axiom sayısı, süre
5. **Ablation**: kural katmanı olmadan vs. ile — kaç ölçüm doğru sınıflanıyor
6. **Uzman doğrulaması**: 2–3 çevre mühendisi, atfedilen kaynaklar için Cohen's kappa
7. **Karşılaştırma**: SSN/OPO/WaWO+ ile Table 1 üzerinden nitel karşılaştırma

### WP7 — Şekiller ve tablolar (Hafta 7–8)
- F1: Kavramsal mimari (5 veri katmanı → KG → reasoning → DSS çıktısı)
- F2: Modül diyagramı + import grafiği
- F3: Ana sınıf hiyerarşisi (WebVOWL, temiz render — mevcut `ProjectOwl_v4.svg` iyi bir başlangıç)
- F4: **Ergene haritası** — istasyonlar, RQ ile renklendirilmiş, deşarj noktaları (QGIS/folium)
  *(WP0-2'ye bağlı)*
- F5: Uyum durumu ısı haritası — analit × istasyon, 4 kategori (uyumlu/aşım/tespit altı/**belirsiz**)
- F6: OOPS! before/after
- F7: Reasoning ölçeklenebilirlik
- T1: Literatür boşluk tablosu · T2: Ontoloji metrikleri · T3: CQ→SPARQL · T4: Kaynak atfı sonuçları

### WP8 — Yazım (Hafta 8–10)
Overleaf'te yeni proje (mevcut powerdot deck'i **kullanma**, sıfırdan makale şablonu):
```
paper/
├── main.tex          # MDPI Water şablonu (veya Elsevier elsarticle)
├── refs.bib
├── sections/{01-intro,02-related,03-materials,04-ontology,
│             05-reasoning,06-results,07-evaluation,08-discussion,09-conclusion}.tex
└── figures/
```
Bölüm hedefleri: Intro ~1200 kelime · Related ~1500 · Materials ~1400 · Ontology ~2000 ·
Reasoning ~1200 · Results ~1800 · Evaluation ~1200 · Discussion ~1000 · Conclusion ~400
→ **~12.000 kelime**, Water dergisi için uygun.

Limitations bölümünde dürüstçe belirt: tek kampanya (2017-11), tek havza, ECOSAR tahmini
(ölçülmüş toksisite değil), atıf kuralları hidrolik taşınım modeli değil topolojik yakınlık.

### WP9 — Yayımlama ve submit (Hafta 10–12)
- Ontolojiyi **w3id.org** üzerinden content-negotiation ile yayımla (HTML + TTL + RDF/XML)
- **WIDOCO** ile otomatik dokümantasyon üret
- GitHub repo + **Zenodo DOI** (ontoloji + ABox + scripts + SPARQL sorguları)
- Data availability statement, CRediT yazar katkıları, etik/veri izni beyanı
- Cover letter, 4–5 önerilen hakem
- Submit

---

## Değiştirilecek/oluşturulacak kritik dosyalar

Mevcut (referans, doğrudan değiştirilmeyecek):
- `ProjectOwl_v3.owl` — v5'in başlangıç noktası, ama ağır revizyon
- `Data/*.xlsx` (6 dosya) — ABox kaynağı
- `Developing_An_Ontology.../main.tex` — sadece içerik/figür kaynağı olarak

Yeni yapı:
```
1-OWL/
├── ontology/  ripo-core.ttl, ripo-space.ttl, ripo-chem.ttl,
│              ripo-analytics.ttl, ripo-regulatory.ttl, ripo-ecotox.ttl,
│              ripo.ttl (ana, hepsini import eder), rules/{swrl.ttl,shapes.ttl}
├── data/      raw/ (mevcut xlsx) · processed/ (normalize CSV) · abox/ripo-ergene-abox.ttl
├── scripts/   build_kg.py, run_reasoner.py, run_cq.py, make_figures.py
├── queries/   cq01.rq … cq25.rq
├── eval/      oops_v3.json, oops_v5.json, foops_report.json, reasoner_bench.csv
└── paper/     (yukarıdaki tex yapısı)
```

---

## Doğrulama

1. `python scripts/build_kg.py` → `ripo-ergene-abox.ttl` üretir; triple sayısı ve
   `802 observation / 82 analyte / 222 chemical` sayıları rapor edilir
2. `python scripts/run_reasoner.py` → HermiT tutarlılık **PASS**, unsatisfiable class = 0,
   inferred axiom sayısı ve süre yazılır
3. `pyshacl` ile SHACL validasyonu → 0 violation (veya bilinçli istisnalar listelenir)
4. `python scripts/run_cq.py` → 25/25 CQ boş olmayan ve manuel doğrulanmış sonuç döndürür
5. OOPS! ve FOOPS! web servisine v3 ve v5 yüklenir → critical pitfall sayısı v5'te 0,
   FAIR skoru belirgin artış
6. Manuel çapraz kontrol: veri setindeki 4 `Special to Resource` bileşiği için reasoner'ın
   ürettiği atıf, elle hesaplanan sonuçla birebir eşleşmeli
7. `latexmk -pdf paper/main.tex` → uyarısız derleme, tüm referanslar çözülmüş

---

## Verilen kararlar

- **Katkı ekseni:** ontoloji + SWRL/SHACL akıl yürütme (sansürlü veri semantiği ana özgünlük)
- **Veri:** tezden gelen gerçek Ergene verisi kullanılacak; haklar için proje ekibiyle temas kurulacak
- **Koordinatlar:** bulunabilir → GIS çerçevesi ve harita figürleri planda kalıyor
- **Ontoloji:** modüler yeniden inşa (v3 yamalanmayacak)
- **Zaman/hedef:** 2–3 ay, Q2 (Ecological Informatics → Water / EM&A merdiveni)

## Hâlâ karar bekleyen

| # | Konu | Ne zaman gerekli |
|---|---|---|
| 1 | Ontoloji adı + w3id namespace (`RIPO` / `MPO` / başka) | WP3 başında; kalıcı IRI, sonradan değişmez |
| 2 | Nehir ağı geometrisi (shapefile/GeoJSON) bulunabiliyor mu | WP4; bulunursa IJGI de hedef listesine girer |
| 3 | APC bütçesi | WP9; varsa Water/IJGI (MDPI ~2600 CHF), yoksa EM&A (Springer, abonelik seçeneği ücretsiz) |
| 4 | Eş yazar listesi ve sırası | Submit öncesi |

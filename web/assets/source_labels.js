// Lesbare labels + forklarings-tooltips for datakilder (fetchere) og
// score-drivere. Brukes av app.js på Datakilder-fanen og i setup-kort-
// modalen. Tekniske navn (snake_case) er fortsatt unike IDer i
// backend/YAML — denne fila gjør dem forståelige i UI uten å endre
// bakomliggende kontrakter.
//
// Struktur per oppslag:
//   { label: "kort lesbar tekst", desc: "lengre forklaring (tooltip)" }
//
// Hvis et navn mangler her, faller UI tilbake til det tekniske navnet
// (rendret med <code>...</code> for å signalisere "ikke lokalisert").
//
// Vedlikehold: nye fetchere legges til i FETCHER_LABELS, nye drivere
// i DRIVER_LABELS. Hold tooltipen til én setning som forklarer (a) hvor
// data kommer fra og (b) hva driveren faktisk måler.

(function (root) {
  'use strict';

  // ─── Datakilde-fanen (fetch.yaml-navn) ──────────────────────────────
  const FETCHER_LABELS = {
    // Core
    'prices': {
      label: 'Priser (Yahoo Finance)',
      desc: 'Daglige OHLC + adj-close fra Yahoo Finance. Driver alle teknisk-baserte signaler (EMA/SMA/ATR/range).',
    },
    'fundamentals': {
      label: 'Fundamentaldata (FRED)',
      desc: 'St. Louis Fed FRED-serier — VIX, NFCI, HY OAS, real-yields, M2, ETF-holdings, AAII, F&G osv. Brukes på tvers av macro-/risk-/positioning-familier.',
    },

    // Bot-priser (cTrader live-feed)
    // (ingen fetcher i fetch.yaml — bot-side. Tatt med for symmetri hvis
    // den senere dukker opp i status_report.)

    // CFTC (US futures)
    'cot_disaggregated': {
      label: 'CFTC COT — Disaggregated (US futures)',
      desc: 'CFTC Commitments of Traders, Disaggregated rapport (Producer/MM/Swap/Other). Ukentlig fredag — kjernen i US-positioning-familier.',
    },
    'cot_legacy': {
      label: 'CFTC COT — Legacy (US futures)',
      desc: 'CFTC Commitments of Traders, Legacy rapport (kun Commercial vs Non-Commercial). Brukt der disaggregated-serien er for kort.',
    },

    // Ekstern COT (ICE/Euronext)
    'cot_ice': {
      label: 'ICE COT — Europa (ICE Futures Europe)',
      desc: 'ICE Futures Europe COT-rapport for Brent, kakao, sukker (London) — kun MM net positioning. Komplementerer CFTC for europeiske futures.',
    },
    'cot_euronext': {
      label: 'Euronext COT — Paris (MiFID II)',
      desc: 'Euronext Paris MiFID II positioning-rapport (rapeseed/wheat/corn/sukker). Ukentlig — eneste positioning-data for EU-grain.',
    },

    // Calendar
    'calendar_ff': {
      label: 'Økonomisk kalender (ForexFactory)',
      desc: 'Scheduled high-impact macro-events (NFP, FOMC, CPI etc.) fra ForexFactory. Driver event-distance + scalp-vol-vinduer.',
    },

    // USDA / Brasil
    'wasde': {
      label: 'USDA WASDE (global S/D)',
      desc: 'USDA World Agricultural Supply & Demand Estimates — månedlig stocks-to-use + balanseregnskap for korn/oljefrø/bomull/sukker.',
    },
    'crop_progress': {
      label: 'USDA NASS Crop Progress (US)',
      desc: 'USDA NASS ukentlig vekst-progress og crop conditions (good/excellent-pct) for US-korn/soya/bomull. Mandag-release.',
    },
    'conab': {
      label: 'Conab (Brasil — produksjon)',
      desc: 'Companhia Nacional de Abastecimento — månedlig brasiliansk produksjons-estimat for soya/mais/sukker/kaffe/bomull.',
    },

    // Shipping
    'shipping': {
      label: 'Baltic Shipping (BDI/BDTI/BCTI)',
      desc: 'Baltic Exchange daglige fraktrater (BDI/BDTI/BCTI) som tidligindikator for global commodity-flow.',
    },

    // Sektor (warehouse / energy / sukker / etanol)
    'eia_inventories': {
      label: 'EIA — US energilager (uke)',
      desc: 'US Energy Information Administration ukentlig petroleum-/distillate-/gasoline-/propane-/refinery-data (onsdag).',
    },
    'comex': {
      label: 'COMEX warehouse-stocks (metaller)',
      desc: 'CME COMEX gull/sølv/kobber-warehouse-inventories — ukentlig stress-indikator for metaller.',
    },
    'seismic': {
      label: 'USGS jordskjelv-feed',
      desc: 'US Geological Survey ANSS-katalog — global M≥5 events for mining-disruption + scalp M≥6 trigger.',
    },
    'unica': {
      label: 'UNICA (Brasil sukker/etanol)',
      desc: 'União da Indústria de Cana-de-Açúcar — bi-månedlig Centro-Sul crush + sukker/etanol-mix-data.',
    },

    // Sentiment
    'news_intel': {
      label: 'Markeds-nyheter (Google News RSS)',
      desc: 'Google News-RSS aggregert per instrument, scoret for disruption-severity. Driver news-veto + sentiment-puls.',
    },
    'crypto_sentiment': {
      label: 'Crypto Fear & Greed + CoinGecko',
      desc: 'Daglig F&G-indeks + CoinGecko global market-cap/volume-trender. Brukes på BTC/ETH-instrumenter.',
    },

    // Geo / vær
    'weather': {
      label: 'Vær — daglig (Open-Meteo)',
      desc: 'Open-Meteo daglig forecast/observations for agri-regioner (cornbelt, brazil_coffee, west_africa_cocoa osv.).',
    },
    'weather_monthly': {
      label: 'Vær — månedlig aggregat',
      desc: 'Månedlig vær-aggregat (vannbalanse, tørke-dager) for sukker-/kaffe-/bomulls-regioner. Bygger på ERA5/Open-Meteo.',
    },
    'enso': {
      label: 'NOAA ENSO ONI (kvartal)',
      desc: 'NOAA Oceanic Niño Index — kvartalsvis La Niña/El Niño-regime som driver agri-sesonglogikk.',
    },

    // Sukker-spesifikk (sub-fase 12.11+)
    'anp_ethanol': {
      label: 'ANP (Brasil etanol-pumpe)',
      desc: 'Agência Nacional do Petróleo — månedlig CSV med pumpepris hydrert/anhydrert etanol i Brasil. Driver sukker/etanol-paritet.',
    },
    'usda_psd_india_sugar': {
      label: 'USDA FAS PSD — India sukker',
      desc: 'USDA Foreign Ag Service Production-Supply-Distribution-database (offisiell India-sukker-balanse, månedlig).',
    },
    'isma_india': {
      label: 'ISMA (India Sugar Mills Assoc.)',
      desc: 'Indian Sugar Mills Association månedlige press-releases — uavhengig kryss-sjekk mot USDA PSD.',
    },
    'comtrade_india_sugar': {
      label: 'UN Comtrade — India sukker-eksport',
      desc: 'UN Comtrade månedlig sukker-eksport (HS 1701) fra India — krysser USDA PSD-laget.',
    },

    // Gas-/LNG-storage (EU)
    'agsi': {
      label: 'AGSI EU gas-lager',
      desc: 'Aggregated Gas Storage Inventory — EU-aggregert + per land (DE/IT/NL) gass-lager-fyllingsgrad.',
    },
    'alsi': {
      label: 'ALSI EU LNG-terminal',
      desc: 'Aggregated LNG Storage Inventory — EU LNG-terminal-fyllingsgrad og inn/ut-rate.',
    },
  };

  // ─── Score-drivere (registry-navn) ──────────────────────────────────
  // Tooltip-tekst er hentet fra første linje av driver-funksjonens
  // docstring (auto-generert fra `_REGISTRY` 2026-05-06). Label-feltet
  // er hånd-skrevet for å gi en tydelig, kort identifikator når mange
  // drivere ligner på hverandre (positioning_*, cot_*, eia_*).
  const DRIVER_LABELS = {
    // ── Sentiment / risk-on ──
    'aaii_extreme': { label: 'AAII ekstrem-sentiment', desc: 'AAII Bulls–Bears extreme-contrarian-score (mean-reversion).' },
    'umich_sentiment_z': { label: 'UMich sentiment z', desc: 'University of Michigan Consumer Sentiment z-score. Bull when high.' },
    'cboe_skew_z': { label: 'CBOE SKEW z', desc: 'CBOE SKEW Index z-score — tail-risk priced in equity-options.' },
    'gvz_z': { label: 'GVZ (gull-VIX) z', desc: 'CBOE Gold-ETF VIX (GVZ) z-score. Lav GVZ = bull for Gold/Silver.' },
    'ovx_z': { label: 'OVX (olje-VIX) z', desc: 'CBOE Crude Oil VIX (OVX) z-score. Lav OVX = bull for olje.' },
    'vvix_z': { label: 'VVIX (VIX-of-VIX) z', desc: 'VVIX z-score. Lav = vol-vol-stabilitet, bull for risk.' },
    'move_index_z': { label: 'MOVE z (rate-vol)', desc: 'ICE BofA MOVE Index z-score — Treasury-vol. Lav = rates-stabilitet.' },
    'vix_regime': { label: 'VIX-regime', desc: 'VIX-basert regime-klassifikator, mappet til 0..1.' },
    'vix_term_ratio': { label: 'VIX termstruktur (3M/spot)', desc: 'VIX3M / VIX − 1 — contango/backwardation-regime.' },
    'vix9d_vix_ratio': { label: 'VIX9D/VIX', desc: 'Kortsiktig vol-stress-ratio.' },

    // ── Macro: liquidity & rates ──
    'real_yield': { label: 'Real yield (10Y − BE)', desc: 'DGS10 − T10YIE = real yield. Driver gull/silver-makro.' },
    'net_fed_liq_change': { label: 'Net Fed Liquidity (Δ)', desc: 'WALCL − RRPONTSYD − WTREGEN — Fed-likviditets-impuls.' },
    'nfci_change': { label: 'NFCI (Δ)', desc: 'Chicago Fed National Financial Conditions Index — endring.' },
    'anfci_z': { label: 'ANFCI z', desc: 'Adjusted NFCI z-score — bull når lav (loose conditions).' },
    'hy_oas_change': { label: 'HY OAS 5d-Δ', desc: 'ICE BofA US High Yield OAS 5-dagers endring.' },
    'credit_spread_change': { label: 'BAA−AAA spread', desc: 'Investment-grade kreditt-spread mappet til 0..1.' },
    'm2_yoy': { label: 'M2 YoY%', desc: 'M2 Money Supply 12-måneders YoY %-endring.' },
    'yield_diff_10y': { label: 'US−Foreign 10Y diff', desc: 'US 10Y minus utenlandsk 10Y yield-differensial.' },
    't10y3m': { label: '10Y−3M yield-curve', desc: 'DGS10 − DGS3MO. Bear ved invert; bull ved steep.' },
    't_bill_3mo_yield': { label: '3M T-Bill', desc: '3-Month Treasury Bill rate. Lav rate = bull risk-on.' },
    'treasury_auction_demand': { label: 'Treasury auction-demand', desc: 'US Treasury auction bid-to-cover-ratio z-score.' },
    'fomc_decision_distance': { label: 'Tid til FOMC', desc: 'Tids-buffer til neste FOMC-rentebeslutning (0→1 ramp).' },

    // ── Macro: vekst-/aktivitets-data ──
    'cfnai_3mma': { label: 'CFNAI 3mma', desc: 'CFNAI 3-måneders glidende snitt. Above 0 = above-trend growth.' },
    'industrial_production_yoy': { label: 'INDPRO YoY%', desc: 'US Industrial Production 12m YoY %-change.' },
    'jolts_openings_yoy': { label: 'JOLTS openings YoY', desc: 'Job Openings 12m YoY %-change. Bull when growing.' },
    'initial_claims_z': { label: 'Initial claims z', desc: 'Initial Jobless Claims z-score. Bull når lav.' },
    'continuing_claims_z': { label: 'Continued claims z', desc: 'Continued Jobless Claims z-score. Bull når lav.' },
    'ism_pmi_level': { label: 'ISM Manufacturing PMI', desc: 'ISM Manufacturing PMI headline-level (manuell CSV-fallback).' },
    'dollar_index_breadth': { label: 'USD breadth (8 par)', desc: 'Andel av 8 DEX-pairs som viser USD-styrke over vinduet.' },
    'dxy_chg5d': { label: 'DXY 5d-Δ', desc: '5-dagers % endring i ICE Dollar Index (DX-Y.NYB).' },
    'brl_chg5d': { label: 'USD/BRL 5d-Δ', desc: '5-dagers % endring i USD/BRL (DEXBZUS) — sukker/kaffe-relevant.' },

    // ── Event-surprise (calendar_ff-baserte) ──
    'cpi_surprise': { label: 'CPI surprise', desc: 'CPI m/m actual vs forecast → 0..1.' },
    'pce_surprise': { label: 'Core PCE surprise', desc: 'Core PCE Price Index m/m actual vs forecast.' },
    'gdp_surprise': { label: 'GDP surprise', desc: 'GDP q/q actual vs forecast.' },
    'nfp_surprise': { label: 'NFP surprise', desc: 'Non-Farm Payrolls actual vs forecast.' },
    'event_distance': { label: 'Tid til event', desc: 'Tids-buffer til neste high-impact event (0..1).' },
    'export_event_active': { label: 'Eksport-policy event', desc: 'Aktiv eksport-policy event for commodity (0/1).' },

    // ── Positioning (CFTC TFF/Disaggregated) ──
    'positioning_mm_pct': { label: 'CFTC MM net %-rank', desc: 'Rank-percentile av Managed Money net positioning, 0..1.' },
    'positioning_lev_funds_pct': { label: 'CFTC Leveraged Funds %-rank', desc: 'Rank-percentile av Leveraged Funds (TFF) net positioning.' },
    'positioning_asset_mgr_pct': { label: 'CFTC Asset Manager %-rank', desc: 'Rank-percentile av Asset Manager (TFF) net positioning.' },
    'cot_z_score': { label: 'CFTC MM z (median+MAD)', desc: 'Robust z-score (median+MAD) av MM net positioning.' },
    'cot_oi_change': { label: 'CFTC OI WoW-Δ z', desc: 'COT open_interest week-over-week change z-score.' },
    'cot_concentration_top4': { label: 'CFTC top-4 konsentrasjon', desc: 'Konsentrasjon-av-største-4-traders (CFTC disaggregated).' },
    'cot_swap_dealer_skew': { label: 'CFTC Swap Dealer skew', desc: 'Swap Dealer net-positioning-skew vs OI.' },
    'cot_commercial_extreme': { label: 'CFTC Commercial extrem', desc: 'Commercial-positioning ekstrem-flag (kontrært-signal).' },
    'cot_ice_mm_pct': { label: 'ICE COT MM %-rank', desc: 'Rank-percentile av MM net positioning fra ICE Europe COT.' },
    'cot_euronext_mm_pct': { label: 'Euronext COT MM %-rank', desc: 'Rank-percentile av MM net positioning fra Euronext Paris COT.' },

    // ── Trend / structure / vol-regime ──
    'sma200_align': { label: 'SMA200 align', desc: 'Hvor komfortabelt over SMA200 prisen ligger (0..1).' },
    'momentum_z': { label: 'Momentum z', desc: 'Z-score av close vs rolling mean/std.' },
    'range_position': { label: 'Range-posisjon', desc: 'Prisens posisjon i N-dagers high/low-range.' },
    'vol_regime': { label: 'ATR vol-regime', desc: 'ATR-percentil over lookback-vindu (vol-regime).' },
    'intraday_atr_h1': { label: 'H1 ATR-percentil', desc: 'ATR(14) på H1-bars som kortsiktig vol-percentil.' },

    // ── Analog-historikk ──
    'analog_hit_rate': { label: 'Analog hit-rate', desc: 'Andelen av K-nærmeste naboer der forward_return krysser terskel.' },
    'analog_avg_return': { label: 'Analog snitt-return', desc: 'Gjennomsnittlig forward_return blant K naboer mappet til 0..1.' },

    // ── Etf / fysiske flyt ──
    'etf_holdings_change': { label: 'Fysisk-ETF holdings (Δ)', desc: 'Physical-ETF holdings-endring (gull/sølv).' },

    // ── Vær / klima / agronomi ──
    'weather_stress': { label: 'Vær-stress (region)', desc: 'Kombinert vær-stress-score for instrument-region (siste måned).' },
    'drought_monitor': { label: 'USDM tørke-indeks', desc: 'US Drought Monitor severity (D2+) for grain/softs.' },
    'hdd_cdd_anomaly': { label: 'HDD/CDD anomali', desc: 'Heating/Cooling-Degree-Days mot sesong-norm (NG-bull).' },
    'enso_regime': { label: 'ENSO-regime (ONI)', desc: 'NOAA Oceanic Niño Index → La Niña / Nøytral / El Niño.' },
    'noaa_oni_index': { label: 'NOAA ONI level', desc: 'NOAA Oceanic Niño Index level (kontinuerlig — erstatter enso_regime).' },
    'noaa_enso_forecast_3mo': { label: 'NOAA ENSO 3mnd-prognose', desc: 'IRI ENSO Plumes 3-mnd-forward Niño 3.4 ensemble-mean.' },
    'noaa_pdo_index': { label: 'NOAA PDO', desc: 'NOAA Pacific Decadal Oscillation index level.' },
    'disease_pressure': { label: 'Disease/pest-pressure', desc: 'Score basert på disease/pest-alerts for commodity.' },
    'seasonal_stage': { label: 'Sesongstadium', desc: 'Score basert på gjeldende måned vs monthly_scores-tabell.' },

    // ── Crop-progress / yield (NASS) ──
    'crop_progress_stage': { label: 'NASS crop good/excellent', desc: 'Siste NASS crop-progress good/excellent-prosent.' },
    'nass_grain_stocks_quarterly': { label: 'NASS grain-stocks YoY', desc: 'NASS quarterly grain-stocks YoY-sammenligning.' },
    'nass_yield_corn_yoy': { label: 'NASS Corn yield YoY', desc: 'NASS Corn yield YoY %-endring.' },
    'nass_yield_soy_yoy': { label: 'NASS Soybean yield YoY', desc: 'NASS Soybean yield YoY %-endring.' },

    // ── USDA WASDE / FAS ──
    'wasde_s2u_change': { label: 'WASDE stocks-to-use Δ', desc: 'Endring i WASDE stocks-to-use ratio.' },
    'fas_exports': { label: 'USDA FAS US-eksport WoW', desc: 'USDA FAS ukentlig US-eksport WoW-endring.' },
    'usda_psd_yoy': { label: 'USDA PSD YoY', desc: 'USDA FAS PSD YoY-endring (production/exports/imports).' },

    // ── Brasil agri ──
    'conab_yoy': { label: 'Conab produksjon YoY', desc: 'Conab Brasil YoY-endring i produksjon.' },
    'cecafe_export_change': { label: 'Cecafé kaffe-eksport (mnd)', desc: 'Cecafé månedlig kaffe-eksport-endring (Coffee).' },
    'unica_change': { label: 'UNICA sukker-supply-shift', desc: 'UNICA Centro-Sul sukker-supply-shift.' },
    'ethanol_parity_brl': { label: 'Sukker/etanol-paritet', desc: 'Sukker/etanol-paritet i cents/lb (sukker-spesifikk).' },
    'comtrade_export_yoy': { label: 'Comtrade eksport YoY', desc: 'UN Comtrade 12-mo trailing eksport YoY.' },

    // ── Energi (EIA) ──
    'eia_stock_change': { label: 'EIA crude stocks WoW', desc: 'Z-score av WoW % endring i EIA crude-inventories.' },
    'eia_distillate_change': { label: 'EIA distillate stocks', desc: 'Distillate Fuel Oil Stocks (WDISTUS1) WoW z.' },
    'eia_propane_change': { label: 'EIA propane stocks', desc: 'Propane/Propylene Stocks (WPRSTUS1) WoW z.' },
    'eia_imports_crude': { label: 'EIA crude imports', desc: 'US Imports of Crude Oil (WCRIMUS2).' },
    'eia_gasoline_demand': { label: 'EIA gasoline demand', desc: 'Finished Motor Gasoline Supplied (WGFUPUS2) — demand-proxy.' },
    'eia_petroleum_supplied': { label: 'EIA petroleum supplied', desc: 'US Petroleum Products Supplied (WRPUPUS2) — total demand-proxy.' },
    'eia_refinery_utilization_z': { label: 'EIA refinery utilization', desc: 'Refiner Net Inputs of Crude Oil (WPULEUS3) z-score.' },
    'eia_natgas_processing': { label: 'EIA NGPL production MoM', desc: 'US NGPL Production Gaseous Equivalent (N9060US2) MoM-z.' },

    // ── Gas-/LNG-storage (EU) ──
    'agsi_storage_pct': { label: 'AGSI EU storage-fyllgrad', desc: 'AGSI EU-aggregert gas-storage fyllingsgrad.' },
    'agsi_germany_pct': { label: 'AGSI Tyskland storage', desc: 'AGSI Germany gas-storage fyllingsgrad.' },
    'agsi_italy_pct': { label: 'AGSI Italia storage', desc: 'AGSI Italy gas-storage fyllingsgrad.' },
    'agsi_netherlands_pct': { label: 'AGSI Nederland storage', desc: 'AGSI Netherlands gas-storage fyllingsgrad.' },
    'agsi_injection_rate': { label: 'AGSI injection-rate z', desc: 'AGSI injection-rate (TWh/dag) z-score.' },
    'agsi_withdrawal_rate': { label: 'AGSI withdrawal-rate z', desc: 'AGSI withdrawal-rate (TWh/dag) z-score.' },
    'alsi_eu_pct': { label: 'ALSI EU LNG-fyllgrad', desc: 'ALSI EU LNG-terminal fyllingsgrad.' },
    'alsi_storage_change': { label: 'ALSI WoW storage-Δ', desc: 'ALSI inventory WoW % endring.' },

    // ── Metaller / mining / shipping ──
    'comex_stress': { label: 'COMEX warehouse-stress', desc: 'COMEX warehouse-stress score (gull/sølv/kobber).' },
    'mining_disruption': { label: 'Mining-disruption', desc: 'USGS-events i mining-regioner mappet til disruption-score.' },
    'seismic_chile_peru_copper': { label: 'Chile/Peru kobber-seismic', desc: 'M ≥ 5.5 jordskjelv i Chile/Peru kobber-regioner siste 7d.' },
    'seismic_m6_global_24h': { label: 'Global M≥6 (24t)', desc: 'Globale M ≥ 6 jordskjelv siste 24t.' },
    'shipping_pressure': { label: 'Baltic shipping-press', desc: '% endring i Baltic-shipping-indeks over vindu.' },
    'iip_supply_unavailability': { label: 'IIP supply-unavailability', desc: 'IIP REMIT aggregert supply-unavailability.' },

    // ── Misc / sentiment-veto ──
    'news_intel_severity_veto': { label: 'News-veto (severity)', desc: 'Veto-driver basert på news_intel disruption_score.' },
  };

  // ─── Helpers ─────────────────────────────────────────────────────────
  function _fallback(name) {
    return { label: name, desc: '', isFallback: true };
  }

  function getFetcherLabel(name) {
    return FETCHER_LABELS[name] || _fallback(name);
  }

  function getDriverLabel(name) {
    return DRIVER_LABELS[name] || _fallback(name);
  }

  // Eksponer på window. ES-modul-syntax er ikke i bruk i dette UI-laget
  // (jevn med admin.js / app.js — load via <script> uten type="module").
  root.BedrockSourceLabels = {
    FETCHER_LABELS,
    DRIVER_LABELS,
    getFetcherLabel,
    getDriverLabel,
  };
})(window);

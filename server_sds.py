# server_sds.py — High-Performance MCP Tools Server for SDS Retrieval Agent
# Accurately retrieves official Safety Data Sheets directly from supplier domains.

from __future__ import annotations

import base64
import os
import re
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from fastmcp import FastMCP

mcp = FastMCP("SDSTools")

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 12

# Comprehensive supplier domain mappings (including subdomains and brand families)
SUPPLIER_DOMAINS = {
    # 1. Life Science & Lab Chemicals
    "thermofisher": ["thermofisher.com", "fishersci.com", "assets.fishersci.com", "assets.thermofisher.com", "alfa.com", "acros.com", "thermoscientific.com", "oxoid.com", "remel.com"],
    "fishersci": ["fishersci.com", "thermofisher.com", "assets.fishersci.com"],
    "sigma": ["sigmaaldrich.com", "merckmillipore.com", "emdmillipore.com", "milliporesigma.com", "emdchemicals.com"],
    "sigmaaldrich": ["sigmaaldrich.com", "merckmillipore.com", "emdmillipore.com", "milliporesigma.com"],
    "millipore": ["emdmillipore.com", "sigmaaldrich.com", "merckmillipore.com", "milliporesigma.com", "emdchemicals.com", "emdmaterials.com"],
    "merck": ["merckmillipore.com", "sigmaaldrich.com", "emdmillipore.com", "milliporesigma.com", "emdchemicals.com"],
    "enamine": ["enamine.net", "enamine.enamine.net", "enaminestore.com"],
    "pharmablock": ["pharmablock.com"],
    "bld": ["bldpharm.com", "file.bldpharm.com", "us-file.bldpharm.com"],
    "bldpharm": ["bldpharm.com", "file.bldpharm.com", "us-file.bldpharm.com"],
    "avantor": ["vwr.com", "avantorsciences.com", "media.vwr.com", "jtbaker.com", "macronfinechemicals.com"],
    "jtbaker": ["jtbaker.com", "avantorsciences.com", "vwr.com", "macronfinechemicals.com"],
    "tci": ["tcichemicals.com", "tci-america.com"],
    "tcichemicals": ["tcichemicals.com", "tci-america.com"],
    "tciamerica": ["tcichemicals.com", "tci-america.com"],
    "tci-america": ["tcichemicals.com", "tci-america.com"],

    # 2. Industrial, Specialty Chemicals & Polymers
    "3m": ["3m.com", "3m.ca", "3mcanada.ca", "multimedia.3m.com", "sds.3m.com", "imation.com"],
    "crc": ["crcindustries.com", "se.crcindustries.eu", "crcind.com", "crcindustries.ca"],
    "gojo": ["gojo.com", "purell.com"],
    "purell": ["purell.com", "gojo.com"],
    "hach": ["hach.com", "ie.hach.com", "support.hach.com", "de.hach.com", "hach.ca"],
    "momentive": ["momentive.com", "sds.momentive.com"],
    "unifrax": ["unifrax.com", "alkegen.com"],
    "alkegen": ["alkegen.com", "unifrax.com"],
    "castrol": ["castrol.com", "msdspds.castrol.com", "bp.com"],
    "tribol": ["castrol.com", "msdspds.castrol.com"],
    "akzonobel": ["akzonobel.com", "international-marine.com", "sikkens.com"],
    "basf": ["basf.com", "download.basf.com", "plastics.basf.com", "agro.basf.com"],
    "clariant": ["clariant.com"],
    "colgate": ["colgatepalmolive.com", "colgate.com"],
    "scjohnson": ["scjohnson.com", "scjp.com", "whatsinsidescjohnson.com"],
    "dow": ["dow.com", "consumer.dow.com"],
    "dowcorning": ["dow.com", "consumer.dow.com"],
    "axalta": ["axalta.com", "axaltacs.com"],
    "kodak": ["kodak.com", "graphics.kodak.com", "eastmankodak.com"],
    "exxon": ["exxonmobil.com", "mobil.com", "imperialoil.ca", "msds.exxonmobil.com"],
    "exxonmobil": ["exxonmobil.com", "mobil.com", "imperialoil.ca", "msds.exxonmobil.com"],
    "mobil": ["mobil.com", "exxonmobil.com", "msds.exxonmobil.com"],
    "imperialoil": ["imperialoil.ca", "exxonmobil.com", "mobil.com"],
    "esso": ["esso.ca", "esso.com", "exxonmobil.com", "mobil.com"],
    "honeywell": ["lab-honeywell.com", "honeywell.com", "prod-edam.honeywell.com", "honeywell-pmt.com", "alliedsignal.com"],
    "valspar": ["valspar.com", "valsparpaint.com", "sherwin-williams.com"],
    "henkel": ["henkel.com", "sds.henkel.com", "mysds.henkel.com", "loctite.com", "henkel-adhesives.com", "henkel.ca", "loctite.ca", "felpro.com"],
    "loctite": ["henkel.com", "sds.henkel.com", "mysds.henkel.com", "loctite.com", "henkel-adhesives.com", "henkel.ca", "loctite.ca", "felpro.com"],
    "tyco": ["ansul.com", "johnsoncontrols.com", "tyco.com", "tyco-fire.com"],
    "ansul": ["ansul.com", "johnsoncontrols.com", "tyco.com"],
    "johnsoncontrols": ["johnsoncontrols.com", "ansul.com", "tyco.com"],
    "clorox": ["clorox.com", "thecloroxcompany.com", "cloroxpro.com"],
    "procter": ["pg.com", "pgpro.com", "pgbrands.com"],
    "pg": ["pg.com", "pgpro.com", "pgbrands.com"],
    "reckitt": ["reckitt.com", "rbeuroinfo.com", "lysol.com"],
    "pfizer": ["pfizer.com", "pfizerpro.com"],
    "dap": ["dap.com"],
    "bondex": ["dap.com"],
    "dynaflux": ["dynaflux.com"],
    "epminerals": ["epminerals.com", "celatom.com"],
    "federalprocess": ["gasoila.com", "federalprocess.com"],
    "gasoila": ["gasoila.com", "federalprocess.com"],
    "lubriplate": ["lubriplate.com"],
    "itw": ["itwpolymers.com", "itwprobrands.com", "devcon.com", "plexusadhesives.com", "itwcc.com", "lpslabs.com", "dykem.com"],
    "devcon": ["devcon.com", "itwpolymers.com", "itwprobrands.com"],
    "plexus": ["plexusadhesives.com", "itwpolymers.com"],
    "philadelphiaresins": ["itwpolymers.com", "chockfast.com"],
    "itwprobrands": ["itwprobrands.com", "lpslabs.com", "dykem.com"],
    "lps": ["lpslabs.com", "itwprobrands.com"],
    "dykem": ["dykem.com", "itwprobrands.com"],
    "whitlam": ["jcwhitlam.com"],
    "kano": ["kanolabs.com", "kroil.com"],
    "kleenflo": ["kleenflo.com", "kleenflo.ca"],
    "lincoln": ["lincolnelectric.com"],
    "lincolnelectric": ["lincolnelectric.com"],
    "hobart": ["hobartbrothers.com"],
    "hobartbrothers": ["hobartbrothers.com"],
    "weldon": ["weldon.com", "ipscorp.com"],
    "ipsweldon": ["weldon.com", "ipscorp.com"],
    "mgchemicals": ["mgchemicals.com"],
    "chemaqua": ["chemaqua.com", "nch.com"],
    "nch": ["nch.com", "chemaqua.com"],
    "msa": ["msasafety.com"],
    "msasafety": ["msasafety.com"],
    "videojet": ["videojet.com"],
    "masterfluid": ["masterfluids.com", "masterfluidsolutions.com"],
    "recochem": ["recochem.com"],
    "karcher": ["karcher.com", "hotsy.com"],
    "hotsy": ["hotsy.com", "karcher.com"],
    "aervoe": ["aervoe.com"],
    "solvay": ["solvay.com", "syensqo.com"],
    "dupont": ["dupont.com"],
    "airliquide": ["airliquide.com", "airgas.com", "myairgas.com", "industry.airliquide.us"],
    "evonik": ["evonik.com", "msds.evonik.com", "corporate.evonik.com"],
}

JURISDICTION_NAMES = {
    "CA": "Canada", "CANADA": "Canada",
    "US": "United States", "USA": "United States", "UNITED STATES": "United States",
    "MX": "Mexico", "MEXICO": "Mexico",
    "GB": "United Kingdom", "UK": "United Kingdom", "UNITED KINGDOM": "United Kingdom",
    "DE": "Germany", "GERMANY": "Germany",
    "FR": "France", "FRANCE": "France",
    "ES": "Spain", "SPAIN": "Spain",
    "IT": "Italy", "ITALY": "Italy",
    "AU": "Australia", "AUSTRALIA": "Australia",
    "JP": "Japan", "JAPAN": "Japan",
    "CN": "China", "CHINA": "China",
    "IN": "India", "INDIA": "India",
    "MY": "Malaysia", "MALAYSIA": "Malaysia",
    "BE": "Belgium", "BELGIUM": "Belgium",
    "NL": "Netherlands", "NETHERLANDS": "Netherlands",
    "EU": "Europe", "GHS": "GHS"
}

JURISDICTION_TO_ISO2 = {
    "UNITED STATES": "US", "USA": "US", "US": "US",
    "CANADA": "CA", "CA": "CA",
    "UNITED KINGDOM": "GB", "UK": "GB", "GB": "GB",
    "GERMANY": "DE", "DE": "DE",
    "FRANCE": "FR", "FR": "FR",
    "ITALY": "IT", "IT": "IT",
    "SPAIN": "ES", "ES": "ES",
    "AUSTRALIA": "AU", "AU": "AU",
    "JAPAN": "JP", "JP": "JP",
    "CHINA": "CN", "CN": "CN",
    "INDIA": "IN", "IN": "IN",
    "MALAYSIA": "MY", "MY": "MY",
    "BELGIUM": "BE", "BE": "BE",
    "NETHERLANDS": "NL", "NL": "NL",
    "MEXICO": "MX", "MX": "MX",
    "RUSSIA": "RU", "RU": "RU",
    "TURKEY": "TR", "TR": "TR",
    "KOREA": "KR", "SOUTH KOREA": "KR", "KR": "KR",
    "BRAZIL": "BR", "BR": "BR",
    "EU": "EU", "GHS": "US",
}

LANGUAGE_NAMES = {
    "FR": "French", "FRENCH": "French",
    "EN": "English", "ENGLISH": "English",
    "ES": "Spanish", "SPANISH": "Spanish",
    "DE": "German", "GERMAN": "German",
    "IT": "Italian", "ITALIAN": "Italian",
    "ZH": "Chinese", "CHINESE": "Chinese", "CHINESE (SIMPLIFIED)": "Chinese", "CHINESE SIMPLIFIED": "Chinese",
    "JA": "Japanese", "JAPANESE": "Japanese",
    "PT": "Portuguese", "PORTUGUESE": "Portuguese",
    "NL": "Dutch", "DUTCH": "Dutch",
    "RU": "Russian", "RUSSIAN": "Russian",
    "TR": "Turkish", "TURKISH": "Turkish",
    "KO": "Korean", "KOREAN": "Korean",
}

LANGUAGE_TO_ISO2 = {
    "ENGLISH": "en", "EN": "en",
    "FRENCH": "fr", "FR": "fr",
    "SPANISH": "es", "ES": "es",
    "GERMAN": "de", "DE": "de",
    "ITALIAN": "it", "IT": "it",
    "CHINESE": "zh", "ZH": "zh", "CHINESE (SIMPLIFIED)": "zh", "CHINESE SIMPLIFIED": "zh",
    "JAPANESE": "ja", "JA": "ja",
    "PORTUGUESE": "pt", "PT": "pt",
    "DUTCH": "nl", "NL": "nl",
    "RUSSIAN": "ru", "RU": "ru",
    "TURKISH": "tr", "TR": "tr",
    "KOREAN": "ko", "KO": "ko",
}


# ==========================================================================
# Helpers
# ==========================================================================

def _sanitise(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', s)[:120]

def _clean_chemical_name(name: str) -> str:
    """Removes grade/purity text (e.g. ', ACS reagent', ', 99.8%') for clean search matching."""
    if not name:
        return ""
    return re.split(r'[,;\(\[]', name)[0].strip()

def _is_valid_domain(url: str, allowed_domains: list[str]) -> bool:
    if not url:
        return False
    try:
        netloc = urlparse(url).netloc.lower()
        return any(domain in netloc for domain in allowed_domains)
    except Exception:
        return False

def _extract_sds_from_supplier(
    allowed_domains: list[str],
    supplier_name: str,
    product: str,
    part_number: str = "",
    target_jurisdiction: str = "US",
    target_language: str = "EN",
) -> str | None:
    """
    Search within verified supplier domains for official SDS documents matching
    the targeted jurisdiction and language criteria with high precision.
    """
    clean_prod = _clean_chemical_name(product)
    clean_part = (part_number or "").strip()
    
    juris_name = JURISDICTION_NAMES.get(target_jurisdiction.upper(), target_jurisdiction)
    lang_name = LANGUAGE_NAMES.get(target_language.upper(), target_language)

    bad_tokens = [
        "white-paper", "product-overview", "brochure", "-pds-", "tds.pdf", 
        "-tds.pdf", "_tds.pdf", "/tds/", "overview.pdf", "user-guide", 
        "catalog.pdf", "flyer", "bulletin", "manual.pdf", "datasheet.pdf", 
        "technical-data", "spec-sheet", "how-to-download", "safety-data-sheet-old",
        "sds-finder.html", "pds.pdf", "_pds.pdf", "/pds/", "technical_data", "product_data_sheet"
    ]

    queries = []

    # 1. Primary: Targeted queries scoped strictly to supplier domains and official SDS repositories
    for d in allowed_domains[:3]:
        if clean_part and clean_prod:
            queries.append(f"site:{d} {clean_prod} {clean_part} SDS pdf")
            queries.append(f"site:{d} {clean_part} safety data sheet {lang_name}")
            queries.append(f"site:{d} {clean_part} SDS")
        elif clean_part:
            queries.append(f"site:{d} {clean_part} SDS pdf")
            queries.append(f"site:{d} {clean_part} safety data sheet")
            queries.append(f"site:{d} {clean_part}")
        elif clean_prod:
            queries.append(f"site:{d} {clean_prod} SDS pdf")
            queries.append(f"site:{d} {clean_prod} safety data sheet")

    # 2. Broader supplier & verified distributor queries with exact part numbers
    if clean_part and clean_prod:
        queries.append(f"{supplier_name} {clean_prod} {clean_part} safety data sheet {lang_name} {juris_name} pdf")
        queries.append(f"{supplier_name} {clean_part} SDS {lang_name} {juris_name} pdf")
        queries.append(f"{clean_prod} {clean_part} Safety Data Sheet pdf")
        queries.append(f"{supplier_name} {clean_part} SDS")
    elif clean_part:
        queries.append(f"{supplier_name} {clean_part} safety data sheet {lang_name} {juris_name} pdf")
        queries.append(f"{supplier_name} {clean_part} SDS pdf")
        queries.append(f"{supplier_name} {clean_part} safety data sheet")
    elif clean_prod:
        queries.append(f"{supplier_name} {clean_prod} safety data sheet {lang_name} {juris_name} pdf")
        queries.append(f"{supplier_name} {clean_prod} SDS pdf")

    # 1. Primary: Direct Bing Search with Domain Filtering
    for q in queries:
        try:
            bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}"
            r = requests.get(bing_url, headers=HEADERS, timeout=5)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                for a in soup.select('li.b_algo h2 a, li.b_algo a'):
                    raw_href = a.get('href', '')
                    target = raw_href
                    if '/ck/a?!' in raw_href:
                        m = re.search(r'u=a1([A-Za-z0-9_-]+)', raw_href)
                        if m:
                            b64_str = m.group(1)
                            pad = (4 - len(b64_str) % 4) % 4
                            target = base64.urlsafe_b64decode(b64_str + '==='[:pad]).decode('utf-8', errors='ignore')
                    
                    if not target.startswith('http'):
                        continue
                    if any(b in target.lower() for b in bad_tokens):
                        continue
                    
                    is_pdf = ".pdf" in target.lower()
                    is_sds = any(k in target.lower() for k in ["sds", "msds", "safety", "document", "prosds", "directwebview", "download", "ehswww"])
                    is_supplier = any(d in target.lower() for d in allowed_domains)

                    if is_supplier and (
                        (is_pdf and is_sds)
                        or "/sds/" in target.lower()
                        or "/msds" in target.lower()
                        or "store/msds" in target.lower()
                        or "sds-search" in target.lower()
                        or "ehswww" in target.lower()
                        or "document.aspx" in target.lower()
                        or "safety-data-sheet" in target.lower()
                    ):
                        return target
        except Exception:
            pass

    # 2. Fallback: Search via DDGS with verified SDS scoring
    try:
        from ddgs import DDGS
        for dq in queries:
            if not dq:
                continue
            res = list(DDGS().text(dq, max_results=6))
            for item in res:
                t_url = item.get('href', '')
                t_title = item.get('title', '').lower()
                if not t_url.startswith('http') or any(b in t_url.lower() for b in bad_tokens):
                    continue
                
                is_supplier = any(d in t_url.lower() for d in allowed_domains)
                is_pdf = ".pdf" in t_url.lower()
                is_sds = (
                    '/sds/' in t_url.lower()
                    or '/msds' in t_url.lower()
                    or 'safety-data-sheet' in t_url.lower()
                    or 'sds' in t_title
                    or 'safety data sheet' in t_title
                    or 'sicherheitsdatenblatt' in t_title
                    or 'fiche de données de sécurité' in t_title
                    or 'hoja de seguridad' in t_title
                )
                
                if (is_supplier and (is_pdf or is_sds)) or (is_pdf and is_sds):
                    return t_url
    except Exception:
        pass

    return None


def execute_sds_retrieval(
    search_fn,
    product: str,
    part_number: str,
    language: str,
    jurisdiction: str,
    supplier_display_name: str,
) -> dict[str, Any]:
    """Execute direct SDS retrieval."""
    query = part_number.strip() if part_number else product.strip()
    req_l = (language or "EN").upper().strip()
    req_j = (jurisdiction or "US").upper().strip()

    found_url, date_issued = search_fn(
        product=product,
        part_number=part_number,
        target_jurisdiction=req_j,
        target_language=req_l,
    )

    if found_url:
        return {
            "url": found_url,
            "filename": _sanitise(f"{supplier_display_name.lower()}_{query}_{req_l}_{req_j}.pdf"),
            "language": req_l,
            "jurisdiction": req_j,
            "date_issued": date_issued,
            "status": "found",
            "supplier": supplier_display_name,
        }

    return {
        "status": "not_found",
        "supplier": supplier_display_name,
        "url": None,
        "filename": None,
        "language": req_l,
        "jurisdiction": req_j,
        "date_issued": None
    }


# ==========================================================================
# Supplier Tools with Full Priority Hierarchy
# ==========================================================================

@mcp.tool()
def search_thermofisher(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search ThermoFisher / Fisher Scientific for an official SDS."""
    allowed = SUPPLIER_DOMAINS["thermofisher"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        juris_clean = (target_jurisdiction or "US").strip().upper()
        lang_clean = (target_language or "EN").strip().upper()
        country_code = JURISDICTION_TO_ISO2.get(juris_clean, juris_clean[:2] if len(juris_clean) >= 2 else "US")
        lang_code = LANGUAGE_TO_ISO2.get(lang_clean, lang_clean[:2].lower() if len(lang_clean) >= 2 else "en")

        # 1. Direct Fisher Scientific MSDS endpoint by part number
        if part_number:
            clean_part = part_number.strip()
            no_dash = clean_part.replace("-", "").replace("/", "")
            direct_urls = [
                f"https://www.fishersci.com/store/msds?partNumber={urllib.parse.quote(no_dash)}&productDescription=&vendorId=VN00033897&countryCode={country_code}&language={lang_code}",
                f"https://www.fishersci.com/store/msds?partNumber={urllib.parse.quote(clean_part)}&productDescription=&vendorId=VN00033897&countryCode={country_code}&language={lang_code}",
                f"https://www.fishersci.com/store/msds?partNumber={urllib.parse.quote(no_dash)}&countryCode={country_code}&language={lang_code}",
                f"https://www.fishersci.com/store/msds?partNumber={urllib.parse.quote(clean_part)}&countryCode={country_code}&language={lang_code}",
                f"https://www.fishersci.com/store/msds?partNumber={urllib.parse.quote(no_dash)}",
                f"https://www.fishersci.com/store/msds?partNumber={urllib.parse.quote(clean_part)}"
            ]
            for u in direct_urls:
                try:
                    r = requests.get(u, headers=HEADERS, timeout=4, allow_redirects=True)
                    if r.status_code == 200:
                        return u, None
                except Exception:
                    pass

        # 2. Search supplier portal and web
        url = _extract_sds_from_supplier(
            allowed, "ThermoFisher Fisher Scientific", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        if url:
            return url, None

        # 3. Direct Fisher Scientific MSDS search by clean chemical name
        if product:
            clean_p = _clean_chemical_name(product)
            fallback_u = f"https://www.fishersci.com/store/msds?partNumber=&productDescription={urllib.parse.quote(clean_p)}&vendorId=VN00033897&countryCode={country_code}&language={lang_code}"
            return fallback_u, None

        return None, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "ThermoFisher"
    )


@mcp.tool()
def search_sigma_aldrich(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Sigma Aldrich / MilliporeSigma for an official SDS."""
    allowed = SUPPLIER_DOMAINS["sigma"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        juris_clean = (target_jurisdiction or "US").strip().upper()
        lang_clean = (target_language or "EN").strip().upper()
        country_code = JURISDICTION_TO_ISO2.get(juris_clean, juris_clean[:2] if len(juris_clean) >= 2 else "US")
        lang_code = LANGUAGE_TO_ISO2.get(lang_clean, lang_clean[:2].lower() if len(lang_clean) >= 2 else "en")

        # 1. Direct official SDS document URL across Sigma brands (sial for S-prefix items, sigald for numeric catalog items)
        if part_number:
            clean_part = part_number.strip()
            # Sigma Aldrich catalog taxonomy:
            # - Parts starting with 'S' (e.g. S9625, S9888, S7653) are under brand code 'sial'
            # - Numeric parts (e.g. 320331, 179418) are under brand code 'sigald'
            if clean_part.upper().startswith("S"):
                brand = "sial"
            elif clean_part.upper().startswith("A"):
                brand = "aldrich"
            elif clean_part.upper().startswith("F"):
                brand = "fluka"
            else:
                brand = "sigald"

            direct_url = f"https://www.sigmaaldrich.com/{country_code}/{lang_code}/sds/{brand}/{clean_part}?userType=anonymous"
            return direct_url, None

        if product:
            clean_p = _clean_chemical_name(product)
            direct_url = f"https://www.sigmaaldrich.com/{country_code}/{lang_code}/search/{urllib.parse.quote(clean_p)}?focus=products&page=1&perpage=30&sort=relevance&term={urllib.parse.quote(clean_p)}&type=product_name"
            return direct_url, None

        # 2. Scrape supplier portal
        url = _extract_sds_from_supplier(
            allowed, "Sigma Aldrich", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Sigma Aldrich"
    )


@mcp.tool()
def search_millipore(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Millipore / EMD Millipore for an official SDS."""
    allowed = SUPPLIER_DOMAINS["millipore"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Millipore", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Millipore"
    )


@mcp.tool()
def search_enamine(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Enamine catalog for official SDS."""
    allowed = SUPPLIER_DOMAINS["enamine"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        # Enamine official SDS is provided in EU format (English)
        clean_part = part_number.strip() if part_number else ""
        if not clean_part and product:
            # Extract EN code if present in product text
            m = re.search(r'\b(EN\d+[-\w]*)\b', product, re.I)
            if m:
                clean_part = m.group(1).strip()

        if clean_part:
            # 1. Try EnamineStore official product certificate / SDS API
            try:
                api_url = "https://enaminestore.com/api/v1/catalog/productcertificate"
                payload = {"code": clean_part, "lang": "en", "type": "MSDS", "dgBlock": False}
                api_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": f"https://enaminestore.com/catalog/{clean_part}",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json"
                }
                r = requests.post(api_url, json=payload, headers=api_headers, timeout=6)
                if r.status_code == 200 and len(r.content) > 1000 and r.content.startswith(b'%PDF'):
                    # Direct product page on EnamineStore where the SDS is hosted/downloadable
                    return f"https://enaminestore.com/catalog/{clean_part}?cat=building-blocks", None
            except Exception:
                pass

            # 2. Check direct PDF paths on enamine.net / enaminestore.com
            direct_urls = [
                f"https://enamine.net/files/sds/{clean_part}_SDS.pdf",
                f"https://enamine.net/files/sds/{clean_part}.pdf",
                f"https://enamine.net/download/sds/{clean_part}.pdf",
                f"https://enaminestore.com/catalog/{clean_part}?cat=building-blocks",
                f"https://enaminestore.com/catalog/{clean_part}",
            ]
            for durl in direct_urls:
                try:
                    r = requests.head(durl, headers=HEADERS, timeout=4)
                    if r.status_code == 200:
                        return durl, None
                except Exception:
                    pass

        url = _extract_sds_from_supplier(
            allowed, "Enamine", product, part_number,
            target_jurisdiction="EU",
            target_language="EN"
        )
        if url:
            return url, None

        if clean_part:
            return f"https://enaminestore.com/catalog/{urllib.parse.quote(clean_part)}?cat=building-blocks", None
        elif product:
            clean_p = _clean_chemical_name(product)
            return f"https://enamine.net/hit-locator?search={urllib.parse.quote(clean_p)}", None

        return None, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Enamine"
    )


@mcp.tool()
def search_henkel(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Henkel official SDS portal."""
    allowed = SUPPLIER_DOMAINS["henkel"]
    query = part_number.strip() if part_number else product.strip()

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        if target_jurisdiction != "ANY" and target_language != "ANY":
            try:
                search_url = "https://sds.henkel.com/sds/servlet/GetDoc"
                params = {"pdf": "PDF", "id": query, "lang": target_language.upper(), "country": target_jurisdiction.upper()}
                resp = requests.get(search_url, params=params, headers=HEADERS, timeout=7)
                if resp.status_code == 200 and "application/pdf" in resp.headers.get("Content-Type", ""):
                    return resp.url, None
            except Exception:
                pass

        url = _extract_sds_from_supplier(
            allowed, "Henkel", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Henkel"
    )


@mcp.tool()
def search_solvay(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Solvay / Syensqo for an official SDS."""
    allowed = SUPPLIER_DOMAINS["solvay"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Solvay", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Solvay"
    )


@mcp.tool()
def search_pharmablock(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Pharmablock catalog for an official SDS."""
    allowed = SUPPLIER_DOMAINS["pharmablock"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Pharmablock", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Pharmablock"
    )


@mcp.tool()
def search_bld_pharmatech(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search BLD Pharmatech website for product information and SDS."""
    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        # Extract CAS number or BD number
        tokens = []
        for val in [part_number, product]:
            if val:
                tokens.extend(val.replace(";", " ").replace(",", " ").split())

        for tok in tokens:
            t = tok.strip()
            if re.match(r'^\d{2,7}-\d{2}-\d$', t):
                return f"https://www.bldpharm.com/products/{t}.html", None
            if re.match(r'^BD\d+$', t, re.IGNORECASE):
                return f"https://www.bldpharm.com/search-home.html?keyword={urllib.parse.quote(t.upper())}", None

        if part_number:
            clean_part = part_number.strip()
            return f"https://www.bldpharm.com/search-home.html?keyword={urllib.parse.quote(clean_part)}", None
        elif product:
            clean_p = _clean_chemical_name(product)
            return f"https://www.bldpharm.com/search-home.html?keyword={urllib.parse.quote(clean_p)}", None

        return "https://www.bldpharm.com/search-home.html", None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "BLD Pharmatech"
    )


@mcp.tool()
def search_tci(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search TCI Chemicals for official SDS."""
    allowed = SUPPLIER_DOMAINS["tci"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        if part_number:
            clean_part = part_number.strip()
            juris_clean = target_jurisdiction.strip().upper()
            lang_clean = target_language.strip().upper()
            country_iso = JURISDICTION_TO_ISO2.get(juris_clean, juris_clean[:2] if len(juris_clean) >= 2 else "US")
            lang_iso = LANGUAGE_TO_ISO2.get(lang_clean, lang_clean[:2].lower() if len(lang_clean) >= 2 else "en")
            # Canonical direct product link on TCI Chemicals portal
            direct_url = f"https://www.tcichemicals.com/{country_iso}/{lang_iso}/p/{clean_part}"
            return direct_url, None

        url = _extract_sds_from_supplier(
            allowed, "TCI Chemicals", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "TCI Chemicals"
    )


@mcp.tool()
def search_3m(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search 3M official SDS database."""
    allowed = SUPPLIER_DOMAINS["3m"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        if part_number:
            clean_p = part_number.strip()
            # 3M direct search endpoint pattern
            direct_u = f"https://www.3m.com/3M/en_US/company-us/SDS-search/results/?gsaAction=generalSearch&searchType=sds&q={urllib.parse.quote(clean_p)}"
            return direct_u, None
        url = _extract_sds_from_supplier(
            allowed, "3M", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "3M"
    )


@mcp.tool()
def search_crc_industries(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search CRC Industries / CRC Canada for official SDS."""
    allowed = SUPPLIER_DOMAINS["crc"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "CRC Industries", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "CRC Industries"
    )


@mcp.tool()
def search_gojo_purell(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search GOJO / PURELL / Provon for official SDS."""
    allowed = SUPPLIER_DOMAINS["gojo"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "GOJO PURELL", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "GOJO PURELL"
    )


@mcp.tool()
def search_hach(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Hach Company official portal for SDS."""
    allowed = SUPPLIER_DOMAINS["hach"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Hach", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Hach"
    )


@mcp.tool()
def search_momentive(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Momentive Performance Materials / GE Silicones official SDS."""
    allowed = SUPPLIER_DOMAINS["momentive"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Momentive GE Silicones", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Momentive"
    )


@mcp.tool()
def search_exxon_mobil(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search ExxonMobil / Mobil / Imperial Oil / Esso for official SDS."""
    allowed = SUPPLIER_DOMAINS["exxonmobil"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "ExxonMobil Mobil", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "ExxonMobil"
    )


@mcp.tool()
def search_lubriplate(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Lubriplate Lubricants for official SDS."""
    allowed = SUPPLIER_DOMAINS["lubriplate"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Lubriplate", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Lubriplate"
    )


@mcp.tool()
def search_itw_brands(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search ITW brands (Devcon, Plexus, LPS, Dykem, ProBrands) for official SDS."""
    allowed = SUPPLIER_DOMAINS["itw"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "ITW Devcon Plexus LPS Dykem", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "ITW Brands"
    )


@mcp.tool()
def search_mg_chemicals(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search MG Chemicals for official SDS."""
    allowed = SUPPLIER_DOMAINS["mgchemicals"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "MG Chemicals", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "MG Chemicals"
    )


@mcp.tool()
def search_honeywell(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Honeywell / Honeywell Performance Materials / AlliedSignal for official SDS."""
    allowed = SUPPLIER_DOMAINS["honeywell"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Honeywell", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Honeywell"
    )


@mcp.tool()
def search_kleenflo(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Kleen-Flo Ltd. / Kleen-Flo Tumbler Industries for official SDS."""
    allowed = SUPPLIER_DOMAINS["kleenflo"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "Kleen-Flo", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "Kleen-Flo"
    )


@mcp.tool()
def search_jtbaker(
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search Avantor / JT Baker / Macron fine chemicals for official SDS."""
    allowed = SUPPLIER_DOMAINS["jtbaker"]

    def _supplier_search(product, part_number, target_jurisdiction, target_language):
        url = _extract_sds_from_supplier(
            allowed, "JT Baker Avantor Macron", product, part_number,
            target_jurisdiction=target_jurisdiction,
            target_language=target_language
        )
        return url, None

    return execute_sds_retrieval(
        _supplier_search, product, part_number, language, jurisdiction, "JT Baker"
    )


@mcp.tool()
def search_generic(
    supplier_name: str,
    supplier_website: str,
    product: str,
    part_number: str = "",
    language: str = "EN",
    jurisdiction: str = "US",
) -> dict[str, Any]:
    """Search any supplier website directly for official SDS."""
    try:
        clean_sup = supplier_name.lower().replace(" ", "").replace("-", "")
        matched_domains = None
        for k, v in SUPPLIER_DOMAINS.items():
            if k in clean_sup or clean_sup in k:
                matched_domains = v
                break
        
        if not matched_domains:
            domain = urlparse(supplier_website).netloc.lower() or f"{clean_sup}.com"
            matched_domains = [domain]

        def _supplier_search(product, part_number, target_jurisdiction, target_language):
            url = _extract_sds_from_supplier(
                matched_domains, supplier_name, product, part_number,
                target_jurisdiction=target_jurisdiction,
                target_language=target_language
            )
            return url, None

        return execute_sds_retrieval(
            _supplier_search, product, part_number, language, jurisdiction, supplier_name
        )
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "supplier": supplier_name,
            "url": None,
            "filename": None,
            "language": language,
            "jurisdiction": jurisdiction,
            "date_issued": None
        }


@mcp.tool()
def download_sds(url: str, filename: str) -> dict[str, Any]:
    """Download an SDS PDF from URL to the local downloads folder."""
    try:
        fname = _sanitise(filename) if filename else "sds.pdf"
        if not fname.lower().endswith(".pdf"):
            fname += ".pdf"
        dest = os.path.join(DOWNLOADS_DIR, fname)
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            f.writelines(resp.iter_content(chunk_size=65536))
        return {
            "local_path": dest,
            "filename": fname,
            "size_bytes": os.path.getsize(dest),
            "status": "downloaded",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "local_path": None, "filename": filename}


if __name__ == "__main__":
    mcp.run()

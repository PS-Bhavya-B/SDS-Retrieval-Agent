# mcp_client.py — Reusable async MCP client wrapper for SDS Retrieval Agent

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing_extensions import Self


class McpClientError(RuntimeError):
    pass


class SdsMcpClient:
    """
    Async context manager that manages a stdio MCP session to server_sds.py.

    Usage::

        async with SdsMcpClient() as client:
            tools = await client.list_tools()
            result = await client.call_tool("search_sigma_aldrich", {"product": "ethanol"})
    """

    def __init__(self, server_script: str = "server_sds.py"):
        self._server_script = server_script
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: dict[str, Any] = {}

    async def __aenter__(self) -> Self:
        self._exit_stack = AsyncExitStack()
        python_exe = sys.executable  # use the same venv python
        stdio = await self._exit_stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=python_exe,
                    args=[self._server_script],
                )
            )
        )
        r_in, w_out = stdio
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(r_in, w_out)
        )
        await self._session.initialize()
        tools_list = (await self._session.list_tools()).tools
        self._tools = {t.name: t for t in tools_list}
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()

    # -----------------------------------------------------------------------

    async def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise McpClientError(f"Unknown tool: {name!r}. Available: {list(self._tools)}")
        result = await self._session.call_tool(name, args)
        if result.content:
            raw = result.content[0].text
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
        return json.loads(result.model_dump_json())

    async def search_supplier(
        self,
        supplier: str,
        product: str,
        part_number: str = "",
        language: str = "EN",
        jurisdiction: str = "US",
    ) -> dict[str, Any]:
        """
        Route a search to the correct tool based on the supplier name.
        Falls back to search_generic if no dedicated tool exists.
        """
        supplier_lower = supplier.lower().replace(" ", "").replace("-", "").replace("_", "")

        ROUTING: dict[str, str] = {
            "thermofisher":   "search_thermofisher",
            "fishersci":      "search_thermofisher",
            "fisher":         "search_thermofisher",
            "thermo":         "search_thermofisher",
            "sigmaaldrich":   "search_sigma_aldrich",
            "sigma":          "search_sigma_aldrich",
            "merck":          "search_sigma_aldrich",
            "milliporesigma": "search_millipore",
            "millipore":      "search_millipore",
            "emdmillipore":   "search_millipore",
            "emdperf":        "search_millipore",
            "emdchemicals":   "search_millipore",
            "emscience":      "search_millipore",
            "bdhkodakusa":    "search_millipore",
            "bdhkodak":       "search_millipore",
            "bdh":            "search_millipore",
            "kodak":          "search_millipore",
            "eastmankodak":   "search_millipore",
            "versamark":      "search_millipore",
            "polychromegraphics": "search_millipore",
            "encadinc":       "search_millipore",
            "encad":          "search_millipore",
            "enamine":        "search_enamine",
            "henkel":         "search_henkel",
            "loctite":        "search_henkel",
            "henkelloctite":  "search_henkel",
            "henkelloctitecanada": "search_henkel",
            "felpro":         "search_henkel",
            "felprochem":     "search_henkel",
            "solvay":         "search_solvay",
            "pharmablock":    "search_pharmablock",
            "bldpharmatech":  "search_bld_pharmatech",
            "bld":            "search_bld_pharmatech",
            "tci":            "search_tci",
            "tcichemicals":   "search_tci",
            "tciamerica":     "search_tci",
            "tci-america":    "search_tci",
            "3m":             "search_3m",
            "3mcanada":       "search_3m",
            "3mcanadainc":    "search_3m",
            "3mcanadacompany":"search_3m",
            "imation":        "search_3m",
            "hach":           "search_hach",
            "hachco":         "search_hach",
            "hachcompany":    "search_hach",
            "honeywell":      "search_honeywell",
            "honeywellintl":  "search_honeywell",
            "honeywellperf":  "search_honeywell",
            "alliedsignal":   "search_honeywell",
            "alliedchem":     "search_honeywell",
            "alliedchemical": "search_honeywell",
            "kleenflo":       "search_kleenflo",
            "kleenfloltd":    "search_kleenflo",
            "kleenflotumbler":"search_kleenflo",
            "avantor":        "search_jtbaker",
            "avantorperformancematerials": "search_jtbaker",
            "jtbaker":        "search_jtbaker",
            "mallinckrodt":   "search_jtbaker",
            "starbiochemicals": "search_jtbaker",
            "macron":         "search_jtbaker",
            "itw":            "search_itw_brands",
            "itwprobrands":   "search_itw_brands",
            "lps":            "search_itw_brands",
            "lpslaboratories":"search_itw_brands",
            "emcorp":         "search_itw_brands",
            "emcorpusa":      "search_itw_brands",
            "dykem":          "search_itw_brands",
            "devcon":         "search_itw_brands",
            "plexus":         "search_itw_brands",
        }

        tool_name = None
        for key, tname in ROUTING.items():
            if key in supplier_lower:
                tool_name = tname
                break

        if tool_name and tool_name in self._tools:
            args: dict[str, Any] = {
                "product":    product,
                "part_number": part_number,
                "language":   language,
            }
            if tool_name not in ("search_enamine", "search_pharmablock", "search_bld_pharmatech"):
                args["jurisdiction"] = jurisdiction
            return await self.call_tool(tool_name, args)

        # Generic Playwright fallback — guess website from supplier name
        website = _guess_website(supplier)
        return await self.call_tool("search_generic", {
            "supplier_name":    supplier,
            "supplier_website": website,
            "product":          product,
            "part_number":      part_number,
            "language":         language,
            "jurisdiction":     jurisdiction,
        })

    async def download_sds(self, url: str, filename: str) -> dict[str, Any]:
        return await self.call_tool("download_sds", {"url": url, "filename": filename})


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _guess_website(supplier: str) -> str:
    """Best-effort guess at a supplier's website for the generic fallback."""
    KNOWN: dict[str, str] = {
        "thermofisher": "https://www.thermofisher.com",
        "sigma":        "https://www.sigmaaldrich.com",
        "millipore":    "https://www.emdmillipore.com",
        "enamine":      "https://www.enamine.net",
        "henkel":       "https://www.henkel.com",
        "solvay":       "https://www.solvay.com",
        "pharmablock":  "https://www.pharmablock.com",
        "bld":          "https://www.bldpharm.com",
        "tci":          "https://www.tcichemicals.com",
        "tciamerica":   "https://www.tcichemicals.com",
        "3m":           "https://www.3m.com",
        "hach":         "https://www.hach.com",
        "honeywell":    "https://www.honeywell.com",
        "kleenflo":     "https://www.kleenflo.com",
        "itw":          "https://www.itwprobrands.com",
        "avantor":      "https://www.avantorsciences.com",
        "jtbaker":      "https://www.jtbaker.com",
        "kodak":        "https://www.kodak.com",
    }
    s = supplier.lower()
    for key, url in KNOWN.items():
        if key in s:
            return url
    slug = re.sub(r"[^a-z0-9]", "", s)
    return f"https://www.{slug}.com"


import re

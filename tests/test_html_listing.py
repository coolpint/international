import unittest

from bs4 import BeautifulSoup

from src.monitor.models import SourceConfig
from src.monitor.sources import _extract_html_listing_links


class HtmlListingTests(unittest.TestCase):
    def test_extract_html_listing_links_applies_domain_and_url_filters(self) -> None:
        source = SourceConfig(
            id="ustr_press_releases",
            label="USTR Press Releases",
            type="html_listing",
            enabled=True,
            list_url="https://ustr.gov/about-us/policy-offices/press-office/press-releases",
            max_items=20,
            options={
                "allowed_domains": ["ustr.gov"],
                "allowed_url_patterns": ["/press-office/press-releases/"],
                "deny_url_patterns": ["/fact-sheets/"],
            },
        )
        soup = BeautifulSoup(
            """
            <div class="view-content">
              <div class="views-row">
                <a href="/about/policy-offices/press-office/press-releases/2026/march/example-release">Keep</a>
              </div>
              <div class="views-row">
                <a href="/about/policy-offices/press-office/fact-sheets/2026/march/example-fact-sheet">Drop fact sheet</a>
              </div>
              <div class="views-row">
                <a href="https://external.example.com/about/policy-offices/press-office/press-releases/2026/march/external">Drop external</a>
              </div>
              <div class="views-row">
                <a href="/trade-topics/wto-reform">Drop topic page</a>
              </div>
              <div class="views-row">
                <a href="/about/policy-offices/press-office/press-releases/2026/march/example-release">Duplicate</a>
              </div>
            </div>
            """,
            "html.parser",
        )

        urls = _extract_html_listing_links(source.list_url or "", soup, "a[href]", source)

        self.assertEqual(
            urls,
            ["https://ustr.gov/about/policy-offices/press-office/press-releases/2026/march/example-release"],
        )

    def test_china_mfa_selector_keeps_only_dated_statement_links(self) -> None:
        source = SourceConfig(
            id="china_mfa_spokesperson_zh",
            label="中华人民共和国外交部发言人",
            type="html_listing",
            enabled=True,
            list_url="https://www.mfa.gov.cn/web/fyrbt_673021/dhdw_673027/index.shtml",
            max_items=20,
            options={
                "allowed_domains": ["www.mfa.gov.cn"],
                "allowed_url_patterns": ["/web/fyrbt_673021/dhdw_673027/"],
            },
        )
        soup = BeautifulSoup(
            """
            <a href="./">Listing page</a>
            <a href="./202607/t20260718_11985612.shtml">Keep dated statement</a>
            <a href="/web/zwjg_674741/example.shtml">Drop navigation</a>
            """,
            "html.parser",
        )

        urls = _extract_html_listing_links(
            source.list_url or "",
            soup,
            'a[href^="./20"]',
            source,
        )

        self.assertEqual(
            urls,
            [
                "https://www.mfa.gov.cn/web/fyrbt_673021/dhdw_673027/202607/t20260718_11985612.shtml"
            ],
        )


if __name__ == "__main__":
    unittest.main()

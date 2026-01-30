"""
IP Resolver Module

Uses MaxMind GeoLite2 databases to resolve IP addresses to company/organization information.
Also supports reverse DNS lookups as a fallback.
"""

import logging
import socket
import json
import re
import tarfile
import requests
from pathlib import Path
from datetime import datetime, timezone

from config import Config
from lead_registry import get_connection, utc_now, normalize_domain

logger = logging.getLogger(__name__)

# Try to import geoip2, provide fallback if not installed
try:
    import geoip2.database
    GEOIP2_AVAILABLE = True
except ImportError:
    GEOIP2_AVAILABLE = False
    logger.warning("geoip2 not installed. Run: pip install geoip2")


class IPResolver:
    """Resolves IP addresses to company/organization information."""

    def __init__(self):
        self.city_reader = None
        self.asn_reader = None
        self._init_readers()

    def _init_readers(self):
        """Initialize MaxMind database readers if available."""
        if not GEOIP2_AVAILABLE:
            logger.warning("geoip2 not available, using fallback methods only")
            return

        # City database
        if Config.MAXMIND_DB_PATH.exists():
            try:
                self.city_reader = geoip2.database.Reader(str(Config.MAXMIND_DB_PATH))
                logger.info(f"Loaded MaxMind City database: {Config.MAXMIND_DB_PATH}")
            except Exception as e:
                logger.error(f"Failed to load City database: {e}")

        # ASN database (contains organization info)
        if Config.MAXMIND_ASN_DB_PATH.exists():
            try:
                self.asn_reader = geoip2.database.Reader(str(Config.MAXMIND_ASN_DB_PATH))
                logger.info(f"Loaded MaxMind ASN database: {Config.MAXMIND_ASN_DB_PATH}")
            except Exception as e:
                logger.error(f"Failed to load ASN database: {e}")

    def close(self):
        """Close database readers."""
        if self.city_reader:
            self.city_reader.close()
        if self.asn_reader:
            self.asn_reader.close()

    def lookup_ip(self, ip_address: str) -> dict:
        """
        Look up an IP address and return organization/location info.

        Args:
            ip_address: The IP address to look up

        Returns:
            dict with company_name, domain, city, country, isp, etc.
        """
        result = {
            "ip_address": ip_address,
            "source": "maxmind",
            "company_name": None,
            "domain": None,
            "industry": None,
            "employee_count": None,
            "city": None,
            "region": None,
            "country": None,
            "isp": None,
            "organization": None,
            "is_datacenter": False,
            "is_vpn": False,
            "confidence_score": 0.0,
            "raw_response": {}
        }

        # Skip private/local IPs
        if self._is_private_ip(ip_address):
            result["organization"] = "Private Network"
            result["is_datacenter"] = True
            return result

        # Try MaxMind lookup
        maxmind_result = self._maxmind_lookup(ip_address)
        result.update(maxmind_result)

        # Try reverse DNS as supplementary info
        rdns_result = self._reverse_dns_lookup(ip_address)
        if rdns_result.get("domain") and not result.get("domain"):
            result["domain"] = rdns_result["domain"]
            result["company_name"] = rdns_result.get("company_name") or result.get("company_name")

        # Calculate confidence score
        result["confidence_score"] = self._calculate_confidence(result)

        # Determine if it's a datacenter/hosting IP
        result["is_datacenter"] = self._is_datacenter(result)

        return result

    def _maxmind_lookup(self, ip_address: str) -> dict:
        """Perform MaxMind database lookup."""
        result = {}

        # City/location lookup
        if self.city_reader:
            try:
                response = self.city_reader.city(ip_address)
                result["city"] = response.city.name
                result["region"] = response.subdivisions.most_specific.name if response.subdivisions else None
                result["country"] = response.country.name
                result["raw_response"] = {
                    "city": response.city.name,
                    "country": response.country.iso_code,
                    "latitude": response.location.latitude,
                    "longitude": response.location.longitude
                }
            except Exception as e:
                logger.debug(f"City lookup failed for {ip_address}: {e}")

        # ASN/Organization lookup
        if self.asn_reader:
            try:
                response = self.asn_reader.asn(ip_address)
                org_name = response.autonomous_system_organization
                result["organization"] = org_name
                result["isp"] = org_name

                # Try to extract company name from org
                company_info = self._parse_organization(org_name)
                if company_info:
                    result["company_name"] = company_info.get("company_name")
                    result["domain"] = company_info.get("domain")

                result["raw_response"] = result.get("raw_response", {})
                result["raw_response"]["asn"] = response.autonomous_system_number
                result["raw_response"]["organization"] = org_name
            except Exception as e:
                logger.debug(f"ASN lookup failed for {ip_address}: {e}")

        return result

    def _reverse_dns_lookup(self, ip_address: str) -> dict:
        """Perform reverse DNS lookup."""
        result = {"domain": None, "company_name": None}

        try:
            hostname = socket.gethostbyaddr(ip_address)[0]

            # Extract domain from hostname
            parts = hostname.split(".")
            if len(parts) >= 2:
                # Get the last two parts as domain (e.g., company.com)
                domain = ".".join(parts[-2:])

                # Filter out common hosting/ISP domains
                if not self._is_hosting_domain(domain):
                    result["domain"] = domain
                    result["company_name"] = parts[-2].replace("-", " ").title()

            result["hostname"] = hostname
        except (socket.herror, socket.gaierror):
            pass
        except Exception as e:
            logger.debug(f"Reverse DNS failed for {ip_address}: {e}")

        return result

    def _parse_organization(self, org_name: str) -> dict:
        """
        Try to extract company name and domain from organization string.

        Many ASN organization names follow patterns like:
        - "ACME Corporation"
        - "ACME-INC"
        - "AS12345 Acme Corp"
        """
        if not org_name:
            return None

        result = {}

        # Clean up common prefixes
        cleaned = org_name
        cleaned = re.sub(r"^AS\d+\s*", "", cleaned)  # Remove AS number prefix
        cleaned = re.sub(r"\s*(LLC|Inc|Corp|Ltd|GmbH|SA|SAS|BV)\.?$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if cleaned and not self._is_hosting_provider(cleaned):
            result["company_name"] = cleaned

            # Try to guess domain
            domain_guess = cleaned.lower().replace(" ", "").replace("-", "") + ".com"
            result["domain"] = domain_guess

        return result if result else None

    def _is_private_ip(self, ip_address: str) -> bool:
        """Check if IP is in private/reserved ranges."""
        private_prefixes = [
            "10.", "172.16.", "172.17.", "172.18.", "172.19.",
            "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
            "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
            "172.30.", "172.31.", "192.168.", "127.", "0.", "169.254."
        ]
        return any(ip_address.startswith(prefix) for prefix in private_prefixes)

    def _is_hosting_domain(self, domain: str) -> bool:
        """Check if domain belongs to a hosting/ISP provider."""
        hosting_domains = [
            "amazonaws.com", "googleusercontent.com", "cloudfront.net",
            "azure.com", "digitalocean.com", "linode.com", "vultr.com",
            "hetzner.com", "ovh.net", "rackspace.com", "softlayer.com",
            "comcast.net", "verizon.net", "att.net", "spectrum.net",
            "cox.net", "charter.net", "centurylink.net", "frontier.com"
        ]
        return any(domain.endswith(h) for h in hosting_domains)

    def _is_hosting_provider(self, org_name: str) -> bool:
        """Check if organization is a hosting/cloud provider."""
        hosting_keywords = [
            "amazon", "aws", "google", "microsoft", "azure", "digitalocean",
            "linode", "vultr", "hetzner", "ovh", "rackspace", "cloudflare",
            "akamai", "fastly", "comcast", "verizon", "at&t", "spectrum",
            "cox", "charter", "centurylink", "frontier", "hosting", "datacenter",
            "data center", "cloud", "isp", "telecom", "communications"
        ]
        org_lower = org_name.lower()
        return any(keyword in org_lower for keyword in hosting_keywords)

    def _is_datacenter(self, result: dict) -> bool:
        """Determine if the IP is from a datacenter/hosting provider."""
        org = result.get("organization", "") or ""
        isp = result.get("isp", "") or ""

        return (
            self._is_hosting_provider(org) or
            self._is_hosting_provider(isp) or
            (result.get("domain") and self._is_hosting_domain(result["domain"]))
        )

    def _calculate_confidence(self, result: dict) -> float:
        """Calculate confidence score for the identification (0.0 to 1.0)."""
        score = 0.0

        # Has company name
        if result.get("company_name"):
            score += 0.4

        # Has domain
        if result.get("domain"):
            score += 0.3

        # Has organization from ASN
        if result.get("organization"):
            score += 0.2

        # Has location info
        if result.get("city") and result.get("country"):
            score += 0.1

        # Reduce score if it's a datacenter/hosting
        if result.get("is_datacenter"):
            score *= 0.3

        return min(score, 1.0)

    def resolve_and_store(self, ip_address: str) -> dict:
        """
        Resolve an IP and store the result in the database.

        Returns the resolution result.
        """
        result = self.lookup_ip(ip_address)
        now = utc_now()

        with get_connection() as conn:
            conn.execute("""
                INSERT INTO visitor_ip_resolution (
                    ip_address, source, company_name, domain, industry,
                    employee_count, city, region, country, isp, organization,
                    is_datacenter, is_vpn, confidence_score, resolved_at, raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ip_address,
                result.get("source", "maxmind"),
                result.get("company_name"),
                result.get("domain"),
                result.get("industry"),
                result.get("employee_count"),
                result.get("city"),
                result.get("region"),
                result.get("country"),
                result.get("isp"),
                result.get("organization"),
                1 if result.get("is_datacenter") else 0,
                1 if result.get("is_vpn") else 0,
                result.get("confidence_score", 0),
                now,
                json.dumps(result.get("raw_response", {}))
            ))

        logger.info(f"Resolved IP {ip_address}: {result.get('company_name') or result.get('organization') or 'Unknown'}")
        return result

    def get_cached_resolution(self, ip_address: str) -> dict:
        """Get a previously cached IP resolution from the database."""
        with get_connection() as conn:
            row = conn.execute("""
                SELECT * FROM visitor_ip_resolution
                WHERE ip_address = ?
                ORDER BY resolved_at DESC
                LIMIT 1
            """, (ip_address,)).fetchone()

        if row:
            return dict(row)
        return None


def download_maxmind_databases():
    """
    Download the latest MaxMind GeoLite2 databases.

    Requires MAXMIND_LICENSE_KEY to be set.
    """
    if not Config.MAXMIND_LICENSE_KEY:
        logger.error("MAXMIND_LICENSE_KEY not set. Cannot download databases.")
        return False

    databases = [
        ("GeoLite2-City", Config.MAXMIND_DB_PATH),
        ("GeoLite2-ASN", Config.MAXMIND_ASN_DB_PATH)
    ]

    for db_name, db_path in databases:
        try:
            url = (
                f"https://download.maxmind.com/app/geoip_download?"
                f"edition_id={db_name}&license_key={Config.MAXMIND_LICENSE_KEY}&suffix=tar.gz"
            )

            logger.info(f"Downloading {db_name}...")
            response = requests.get(url, stream=True)
            response.raise_for_status()

            # Save and extract
            tar_path = db_path.parent / f"{db_name}.tar.gz"
            with open(tar_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Extract mmdb file
            with tarfile.open(tar_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith(".mmdb"):
                        member.name = db_path.name
                        tar.extract(member, db_path.parent)
                        break

            # Cleanup tar file
            tar_path.unlink()

            logger.info(f"Downloaded and extracted {db_name} to {db_path}")

        except Exception as e:
            logger.error(f"Failed to download {db_name}: {e}")
            return False

    return True


def resolve_pending_ips(limit: int = 50):
    """
    Resolve IP addresses that haven't been resolved yet.

    This is meant to be run periodically by the scheduler.
    """
    from visitor_tracking import get_unresolved_ips

    resolver = IPResolver()
    unresolved = get_unresolved_ips(limit=limit)

    resolved_count = 0
    for item in unresolved:
        ip = item["ip_address"]

        # Check if already resolved (race condition protection)
        if resolver.get_cached_resolution(ip):
            continue

        result = resolver.resolve_and_store(ip)
        resolved_count += 1

        # Log high-confidence identifications
        if result.get("confidence_score", 0) >= 0.5:
            logger.info(
                f"Identified company: {result.get('company_name')} "
                f"({result.get('domain')}) from IP {ip}"
            )

    resolver.close()
    logger.info(f"Resolved {resolved_count} IP addresses")
    return resolved_count

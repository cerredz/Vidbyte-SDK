"""FILE: vidbyte/tools/builtins/prebuilt/network_addresses.py

PURPOSE: Defines NetworkAddressesToolFunctions, the eight prebuilt tools for IP addresses and networks: address validation with a reason, CIDR network details, membership in a list of networks, subnet splitting, range-to-CIDR conversion, address classification, address and integer conversion, and IPv4 netmask and prefix conversion.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the NETWORK_ADDRESSES category is chosen. Builds on PrebuiltToolSupport in _support.py for the argument error, integer text, and the item cap.
ARCHITECTURE NOTE: Everything is computed with the standard ipaddress module, with no DNS lookup and no socket. Every message for invalid input is written here, never copied from an exception (S017), and subnet counts are computed arithmetically while the subnets themselves come from a lazy generator, so a split into 2^128 networks finishes at once.
FUNCTION INVENTORY: verify_ip_address, cidr_network_details, ip_in_networks, split_cidr_into_subnets, ip_range_to_cidrs, classify_ip_address, convert_ip_address_integer, and convert_ipv4_netmask are the tools; _ipv4_problem finds the first failing IPv4 rule; _read_address and _read_network parse an address or network and name the parameter on failure; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new network tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.31, and its entry in tool_functions. A new IPv4 validation reason adds an IpAddressProblem member and its check in _ipv4_problem, in the order the row gives.
WHAT NOT TO DO IN THIS FILE: 1. Do not resolve host names or open sockets; only address text is read. 2. Do not put an ipaddress exception message into an error; write the problem in the tool's own words. 3. Do not enumerate subnets or addresses to count them; compute counts from prefix lengths.
KNOWN EDGE CASES: The is_private, is_global, and is_reserved flags, and the text of an IPv4-mapped IPv6 address, follow the running Python's tables, which change between releases (EC-26). IPv6 hosts skip only the subnet-router anycast address, so an IPv6 network has one fewer usable host than addresses. An IPv6 address may carry a zone suffix, which its text forms keep; the standard library raises when it explodes such an address, so verify_ip_address explodes the address without its zone and appends the zone.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.31, section 9.2 items 5, 12, and 13, EC-26); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_code_network.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import ipaddress
import re
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_PHRASE_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import IpAddressProblem, IpVersion
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_IPV4_TEXT = re.compile(r"[0-9.]*")
_DECIMAL_INTEGER = re.compile(r"[+-]?[0-9]+")
_PREFIX_TEXT = re.compile(r"/?([0-9]+)")
_IPV4_PART_COUNT = 4
_IPV4_PART_MAXIMUM = 255
_IPV4_ALL_ONES = (1 << ipaddress.IPV4LENGTH) - 1
_BITS_PER_HEX_DIGIT = 4
_ALL_USABLE_HOST_BITS = 1
_RESERVED_HOST_ADDRESSES: MappingProxyType[int, int] = MappingProxyType({4: 2, 6: 1})
_ADDRESS_WIDTHS: MappingProxyType[IpVersion, int] = MappingProxyType({IpVersion.IPV4: ipaddress.IPV4LENGTH, IpVersion.IPV6: ipaddress.IPV6LENGTH})
_ADDRESS_CLASSES: MappingProxyType[IpVersion, type[ipaddress.IPv4Address] | type[ipaddress.IPv6Address]] = MappingProxyType({IpVersion.IPV4: ipaddress.IPv4Address, IpVersion.IPV6: ipaddress.IPv6Address})

_ADDRESS_EXPECTED = "an IPv4 address in dotted-decimal form or an IPv6 address"
_NETWORK_EXPECTED = "a network in CIDR notation, or a bare IPv4 or IPv6 address"
_RANGE_END_EXPECTED = "an address of the same IP version as first_address that does not come before it"
_NETMASK_EXPECTED = "a dotted IPv4 netmask with contiguous one bits, or a prefix length from 0 to 32 with or without a leading slash"

_ADDRESS_DESCRIPTION = "The IP address to read, in IPv4 dotted-decimal form or IPv6 text form. Surrounding spaces are not removed, and an IPv4 part with a leading zero is refused. A text that is not a valid address fails with an error naming address. The text must hold between 1 and 200 characters."
_CIDR_DESCRIPTION = "The network in CIDR notation, an address followed by a slash and a prefix length or a netmask. A bare address without a slash is read as a single-address network. IPv4 and IPv6 are both accepted, and an unreadable network fails with an error naming cidr. The text must hold between 1 and 200 characters."


class NetworkAddressesToolFunctions:
    """The network_addresses category: IP address and CIDR network arithmetic."""

    @staticmethod
    def verify_ip_address(
        address: Annotated[str, Field(description="The text to check as an IP address, given exactly as written. Surrounding spaces are not removed, so they make the address invalid. IPv6 text may use the compressed form, an embedded IPv4 tail, or a zone suffix. The text must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check whether a text is a valid IPv4 or IPv6 address and give its compressed and exploded forms. Use it to validate an address before storing it, or to normalize how an address is written. Text with a colon is read as IPv6, while other text must be four dot-separated decimal parts from 0 to 255 without leading zeros, and reason names the first rule that fails. An invalid address is a successful result with valid set to false and null forms, so the tool fails only on its length cap."""
        # Text with a colon can only be IPv6, so the IPv6 parser
        # decides.
        if ":" in address:
            try:
                parsed: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.IPv6Address(address)
            except ValueError:
                return {"valid": False, "version": None, "compressed": None, "exploded": None, "reason": IpAddressProblem.INVALID_IPV6.value}
        else:
            # Other text is checked against the IPv4 rules in the row's
            # order, so the reason names the first rule that fails.
            problem = NetworkAddressesToolFunctions._ipv4_problem(address)
            if problem is not None:
                return {"valid": False, "version": None, "compressed": None, "exploded": None, "reason": problem.value}
            parsed = ipaddress.IPv4Address(address)
        # The standard library cannot explode an IPv6 address with a
        # zone, so the address is exploded without it and the zone is
        # added back.
        exploded = type(parsed)(int(parsed)).exploded
        if isinstance(parsed, ipaddress.IPv6Address) and parsed.scope_id is not None:
            exploded = f"{exploded}%{parsed.scope_id}"
        return {"valid": True, "version": parsed.version, "compressed": parsed.compressed, "exploded": exploded, "reason": None}

    @staticmethod
    def cidr_network_details(
        cidr: Annotated[str, Field(description=_CIDR_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        strict: Annotated[bool, Field(description="Whether set host bits are an error. When false, the bits below the prefix are cleared to give the network address. When true, an address with host bits set fails with an error naming cidr. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Describe a CIDR network: its normalized form, network and broadcast addresses, netmask and hostmask, prefix length, total and usable address counts, and first and last usable hosts. Use it for subnet planning or to check which addresses a CIDR block covers. A bare address is a single-address network, host bits are cleared unless strict is true, and usable hosts follow the standard library hosts rule. IPv6 networks have a null broadcast address, the counts are exact integer text, and an invalid network fails with an error naming cidr."""
        # Read the network, clearing host bits unless strict is set.
        network = NetworkAddressesToolFunctions._read_network(cidr, "cidr", strict)
        total = network.num_addresses

        # With at most one host bit every address is a usable host;
        # otherwise IPv4 skips the network and broadcast addresses and
        # IPv6 skips only the subnet-router address at the start.
        if network.max_prefixlen - network.prefixlen <= _ALL_USABLE_HOST_BITS:
            usable, first = total, network.network_address
        else:
            usable, first = total - _RESERVED_HOST_ADDRESSES[network.version], network.network_address + 1
        return {
            "network": str(network),
            "network_address": str(network.network_address),
            "broadcast_address": str(network.broadcast_address) if isinstance(network, ipaddress.IPv4Network) else None,
            "netmask": str(network.netmask),
            "hostmask": str(network.hostmask),
            "prefix_length": network.prefixlen,
            "total_addresses": PrebuiltToolSupport.integer_text(total, "cidr"),
            "usable_hosts": PrebuiltToolSupport.integer_text(usable, "cidr"),
            "first_usable": str(first),
            "last_usable": str(first + (usable - 1)),
            "version": network.version,
        }

    @staticmethod
    def ip_in_networks(
        address: Annotated[str, Field(description=_ADDRESS_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        networks: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_PHRASE_CHARS)]], Field(description="The networks to test, each in CIDR notation or as a bare address. Host bits are cleared rather than refused, and IPv4 and IPv6 networks may be mixed. The list must hold between 1 and 10,000 networks. Each network may hold at most 200 characters.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Tell whether an IP address falls inside any network in a list, which networks contain it, and which match is the most specific. Use it for allow lists, routing questions, or checking an address against known ranges. Networks are read with host bits cleared, a network of the other IP version never matches, matches keep input order in normalized form, and the most specific match has the longest prefix, the first one winning ties. An invalid address fails with an error naming address, and an invalid network fails with an error naming networks and its index."""
        # Read the address and every network before matching, so a bad
        # network is reported even when an earlier one already matches.
        target = NetworkAddressesToolFunctions._read_address(address, "address")
        parsed = []
        for index, text in enumerate(networks):
            try:
                parsed.append(ipaddress.ip_network(text, strict=False))
            except ValueError as exc:
                raise PrebuiltToolSupport.argument_error("networks", f"the network at index {index} is not a valid IPv4 or IPv6 network", _NETWORK_EXPECTED) from exc

        # Keep the networks of the same version that hold the address,
        # and pick the longest prefix, the first one on ties.
        matches = [network for network in parsed if network.version == target.version and target in network]
        most_specific = max(matches, key=lambda network: network.prefixlen, default=None)
        return {
            "contained": bool(matches),
            "matching_networks": [str(network) for network in matches],
            "most_specific": str(most_specific) if most_specific is not None else None,
        }

    @staticmethod
    def split_cidr_into_subnets(
        cidr: Annotated[str, Field(description=_CIDR_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        new_prefix_length: Annotated[int, Field(description="The prefix length of the subnets to produce. It must be at least the network's own prefix length, which gives the network itself back. It may be at most 32 for IPv4 and at most 128 for IPv6. Values outside 0 to 128 fail validation.", ge=0, le=ipaddress.IPV6LENGTH)],
    ) -> PrebuiltToolOutput:
        """Split a CIDR network into equal subnets with a longer prefix length, listed in address order. Use it to carve an address block into smaller networks for subnet planning. Host bits of the network are cleared first, and at most 1,000 subnets are listed while count gives the exact total, two to the power of the prefix difference, as integer text. A new prefix shorter than the network's own or longer than the address size fails with an error naming new_prefix_length, and an invalid network fails with an error naming cidr."""
        # Read the network and check that the new prefix fits inside it.
        network = NetworkAddressesToolFunctions._read_network(cidr, "cidr", False)
        if not network.prefixlen <= new_prefix_length <= network.max_prefixlen:
            shorter = new_prefix_length < network.prefixlen
            problem = f"it is shorter than the network's own prefix length of {network.prefixlen}" if shorter else f"it is longer than the {network.max_prefixlen} bits of an IPv{network.version} address"
            raise PrebuiltToolSupport.argument_error("new_prefix_length", problem, f"a prefix length from {network.prefixlen} to {network.max_prefixlen} for this network")

        # Count every subnet arithmetically, and list the first ones
        # from the lazy generator so a huge split never builds them all.
        count = 1 << (new_prefix_length - network.prefixlen)
        subnets, truncated = PrebuiltToolSupport.cap_items(str(subnet) for subnet in network.subnets(new_prefix=new_prefix_length))
        return {"subnets": subnets, "count": PrebuiltToolSupport.integer_text(count, "new_prefix_length"), "truncated": truncated}

    @staticmethod
    def ip_range_to_cidrs(
        first_address: Annotated[str, Field(description="The first address of the range, which the range includes. It is an IPv4 or IPv6 address in standard text form. An invalid address fails with an error naming first_address. The text must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        last_address: Annotated[str, Field(description="The last address of the range, which the range includes. It must be of the same IP version as the first address and must not come before it. An invalid address fails with an error naming last_address. The text must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Convert an inclusive range of IP addresses into the smallest list of CIDR blocks that covers exactly that range. Use it to turn a first and last address into firewall or routing entries. Blocks are listed in address order, both ends are included, and both addresses must be of the same IP version. An invalid first address fails with an error naming first_address, and an invalid last address, a version mismatch, or a last address before the first fails with an error naming last_address."""
        # Read both ends of the range.
        first = NetworkAddressesToolFunctions._read_address(first_address, "first_address")
        last = NetworkAddressesToolFunctions._read_address(last_address, "last_address")

        # Summarize only a well-ordered range of one IP version.
        if int(last) < int(first) and first.version == last.version:
            raise PrebuiltToolSupport.argument_error("last_address", "it comes before first_address", _RANGE_END_EXPECTED)
        if isinstance(first, ipaddress.IPv4Address) and isinstance(last, ipaddress.IPv4Address):
            blocks = [str(block) for block in ipaddress.summarize_address_range(first, last)]
        elif isinstance(first, ipaddress.IPv6Address) and isinstance(last, ipaddress.IPv6Address):
            blocks = [str(block) for block in ipaddress.summarize_address_range(first, last)]
        else:
            raise PrebuiltToolSupport.argument_error("last_address", "it is of a different IP version from first_address", _RANGE_END_EXPECTED)
        return {"cidrs": blocks, "count": len(blocks)}

    @staticmethod
    def classify_ip_address(address: Annotated[str, Field(description=_ADDRESS_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)]) -> PrebuiltToolOutput:
        """Report whether an IP address is private, global, loopback, link-local, multicast, reserved, or unspecified, with its normalized text and version. Use it to decide whether an address is reachable on the public internet or belongs to a special-purpose range. The flags come from the standard library tables of the running Python, which can change between Python releases. For an IPv4-mapped IPv6 address the embedded IPv4 address is given in ipv4_mapped, which is null otherwise, and an invalid address fails with an error naming address."""
        parsed = NetworkAddressesToolFunctions._read_address(address, "address")
        mapped = parsed.ipv4_mapped if isinstance(parsed, ipaddress.IPv6Address) else None
        return {
            "address": str(parsed),
            "version": parsed.version,
            "is_private": parsed.is_private,
            "is_global": parsed.is_global,
            "is_loopback": parsed.is_loopback,
            "is_link_local": parsed.is_link_local,
            "is_multicast": parsed.is_multicast,
            "is_reserved": parsed.is_reserved,
            "is_unspecified": parsed.is_unspecified,
            "ipv4_mapped": str(mapped) if mapped is not None else None,
        }

    @staticmethod
    def convert_ip_address_integer(
        value: Annotated[str, Field(description="The IP address or decimal integer to convert. An address is read in standard IPv4 or IPv6 text form. An integer is plain decimal digits with an optional sign and must fit the chosen version. The text must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        version: Annotated[IpVersion, Field(description="The IP version used when the value is an integer. An integer converts to an IPv4 address when this is ipv4 and to an IPv6 address when this is ipv6. An address text always keeps its own version. The default is ipv4.")] = IpVersion.IPV4,
    ) -> PrebuiltToolOutput:
        """Convert an IP address to its integer value, or an integer to the IP address it encodes, with the version and the zero-padded lowercase hexadecimal form. Use it when addresses are stored, sorted, or compared as numbers. An address text reports its own version, while a decimal integer is read as an address of the chosen version. An integer outside the range of that version, or text that is neither an address nor an integer, fails with an error naming value."""
        # Decimal digits are an integer of the chosen version; any other
        # text must be an address, which keeps its own version.
        if _DECIMAL_INTEGER.fullmatch(value) is not None:
            integer = int(value)
            width = _ADDRESS_WIDTHS[version]
            if not 0 <= integer < 1 << width:
                problem = f"the integer is outside the range of {version.value} addresses"
                raise PrebuiltToolSupport.argument_error("value", problem, f"an integer from 0 to 2 to the power {width} minus 1, or an IP address")
            parsed = _ADDRESS_CLASSES[version](integer)
        else:
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError as exc:
                raise PrebuiltToolSupport.argument_error("value", "the text is neither an IP address nor a decimal integer", "an IPv4 or IPv6 address, or a decimal integer") from exc

        # Write the integer in decimal and in hexadecimal padded to the
        # full width of the address.
        number = int(parsed)
        return {
            "address": str(parsed),
            "integer": PrebuiltToolSupport.integer_text(number, "value"),
            "version": parsed.version,
            "hex": format(number, f"0{parsed.max_prefixlen // _BITS_PER_HEX_DIGIT}x"),
        }

    @staticmethod
    def convert_ipv4_netmask(
        value: Annotated[str, Field(description="The netmask or prefix length to convert. A dotted mask has four decimal parts whose one bits must all come before its zero bits. A prefix length is a number from 0 to 32, with or without a leading slash. The text must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Convert between an IPv4 dotted netmask and a prefix length, giving the prefix length, the netmask, and the hostmask. Use it to translate between netmask notation and CIDR prefix notation. The value may be a dotted mask, a prefix length with a leading slash, or a bare prefix length from 0 to 32. A mask whose one bits are not contiguous, a prefix above 32, or an unreadable value fails with an error naming value."""
        # A prefix length is read directly and must fit an IPv4 address.
        prefix_match = _PREFIX_TEXT.fullmatch(value)
        if prefix_match is not None:
            prefix_length = int(prefix_match.group(1))
            if prefix_length > ipaddress.IPV4LENGTH:
                raise PrebuiltToolSupport.argument_error("value", f"the prefix length is above {ipaddress.IPV4LENGTH}", _NETMASK_EXPECTED)
        else:
            # A dotted mask must be one bits followed only by zero bits,
            # which holds when its inverse plus one is a power of two.
            try:
                inverse = int(ipaddress.IPv4Address(value)) ^ _IPV4_ALL_ONES
            except ValueError as exc:
                raise PrebuiltToolSupport.argument_error("value", "the text is neither a dotted IPv4 netmask nor a prefix length", _NETMASK_EXPECTED) from exc
            if inverse & (inverse + 1):
                raise PrebuiltToolSupport.argument_error("value", "the one bits of the netmask are not contiguous", _NETMASK_EXPECTED)
            prefix_length = ipaddress.IPV4LENGTH - inverse.bit_length()

        # Build both masks from the prefix length.
        network = ipaddress.IPv4Network((0, prefix_length))
        return {"prefix_length": prefix_length, "netmask": str(network.netmask), "hostmask": str(network.hostmask)}

    @staticmethod
    def _ipv4_problem(text: str) -> IpAddressProblem | None:
        """Return the first IPv4 rule the text breaks, in the order of the verify_ip_address row, or None when it is valid."""
        if _IPV4_TEXT.fullmatch(text) is None:
            return IpAddressProblem.INVALID_CHARACTERS
        parts = text.split(".")
        if len(parts) != _IPV4_PART_COUNT:
            return IpAddressProblem.IPV4_WRONG_PART_COUNT
        if "" in parts:
            return IpAddressProblem.IPV4_EMPTY_PART
        if any(len(part) > 1 and part.startswith("0") for part in parts):
            return IpAddressProblem.IPV4_LEADING_ZERO
        if any(int(part) > _IPV4_PART_MAXIMUM for part in parts):
            return IpAddressProblem.IPV4_OCTET_OUT_OF_RANGE
        return None

    @staticmethod
    def _read_address(text: str, parameter_name: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        """Parse an IPv4 or IPv6 address, failing with an error that names the parameter."""
        try:
            return ipaddress.ip_address(text)
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the text is not a valid IPv4 or IPv6 address", _ADDRESS_EXPECTED) from exc

    @staticmethod
    def _read_network(text: str, parameter_name: str, strict: bool) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
        """Parse a CIDR network, clearing host bits unless strict, and fail with an error that names the parameter."""
        try:
            return ipaddress.ip_network(text, strict=strict)
        except ValueError as exc:
            problem = "the text is not a valid network, or it has host bits set while strict is true" if strict else "the text is not a valid IPv4 or IPv6 network"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, _NETWORK_EXPECTED) from exc

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.verify_ip_address,
            cls.cidr_network_details,
            cls.ip_in_networks,
            cls.split_cidr_into_subnets,
            cls.ip_range_to_cidrs,
            cls.classify_ip_address,
            cls.convert_ip_address_integer,
            cls.convert_ipv4_netmask,
        )


__all__ = ["NetworkAddressesToolFunctions"]

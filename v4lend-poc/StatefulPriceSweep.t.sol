// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.30;

import {V4VaultLocalBase} from "test/vault/support/V4VaultLocalBase.sol";
import {IVault} from "src/vault/interfaces/IVault.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

contract NoopTransformerPS {
    fallback() external {}
}

/// @notice Price-moving sweep: same P2 conservation + liquidation liveness under oracle moves.
/// P1 (v2) is relaxed: underwater loans are EXPECTED after a price drop; the invariant is
/// they must be liquidatable (cost>0) and liquidation must SUCCEED when funded.
/// Liveness failure (underwater but cost==0, or liquidate reverts when funded) = lockout signal.
/// P2: debtSharesTotal == sum(loans[i].debtShares) every step.
/// Ops: create / borrow / repay / price halve-double / warp / liquidate-underwater / remove / transfer.
contract StatefulPriceSweep is V4VaultLocalBase {
    NoopTransformerPS internal noop;
    uint256[] internal known;
    mapping(uint256 => bool) internal seen;

    function setUp() public override {
        super.setUp();
        noop = new NoopTransformerPS();
        vault.setTransformer(address(noop), true);
        _deposit(lender, 1_000_000 ether);
    }

    function test_priceSweep(uint256 seed) public {
        uint256 s = seed == 0 ? 1 : seed;
        for (uint256 step; step < 40; step++) {
            s = uint256(keccak256(abi.encode(s, step)));
            _step(s);
            _checkP2(step);
        }
        assertTrue(vault.transformedTokenId() == 0, "mutex stuck");
    }

    function _step(uint256 s) internal {
        uint256 op = s % 10;
        if (op == 0) {
            uint128 liq = uint128(1e10 + (s >> 8) % 1e12);
            try this._mk(liq) returns (uint256 tid) { _track(tid); } catch {}
        } else if (op == 1) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool ok, address o) = _owner(tid);
            if (!ok) return;
            (, uint256 fullValue,,,) = vault.loanInfo(tid);
            if (fullValue == 0) return;
            uint256 amt = fullValue / 2 + ((s >> 16) % (fullValue / 2 + 1));
            vm.prank(o);
            try vault.borrow(tid, amt) {} catch {}
        } else if (op == 2) {
            // oracle price move: halve, double, or reset to 1 ether
            uint256 sel = (s >> 8) % 4;
            if (sel == 0) oracle.setMockPositionValue(0.5 ether);
            else if (sel == 1) oracle.setMockPositionValue(2 ether);
            else if (sel == 2) oracle.setMockPositionValue(0.25 ether);
            else oracle.setMockPositionValue(1 ether);
        } else if (op == 3) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (uint256 debt,,,,) = vault.loanInfo(tid);
            if (debt == 0) return;
            uint256 amt = (s >> 16) % (debt + 1);
            if (amt == 0) return;
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            asset.mint(o, amt);
            vm.startPrank(o);
            asset.approve(address(vault), amt);
            try vault.repay(tid, amt, false) returns (uint256, uint256) {} catch {}
            vm.stopPrank();
        } else if (op == 4) {
            // liquidate every underwater loan (cost>0), funded; must succeed (liveness)
            for (uint256 i; i < known.length; i++) {
                uint256 tid = known[i];
                (,,, uint256 cost,) = vault.loanInfo(tid);
                if (cost == 0) continue;
                asset.mint(liquidator, cost);
                vm.startPrank(liquidator);
                asset.approve(address(vault), cost);
                try vault.liquidate(IVault.LiquidateParams(tid, 0, 0, liquidator, block.timestamp, "")) {} catch (bytes memory err) {
                    // lockout signal: underwater + funded but reverts
                    assertTrue(false, string(abi.encodePacked("LIVENESS BROKEN tid ", _n(tid), " err ", err)));
                }
                vm.stopPrank();
            }
        } else if (op == 5) {
            vm.warp(block.timestamp + 1 hours + ((s >> 8) % 3 days));
        } else if (op == 6) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            vm.prank(o);
            try vault.remove(tid, o, "") {} catch {}
        } else if (op == 7) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            vm.prank(o);
            try vault.approveTransform(tid, address(noop), (s >> 16) % 2 == 0) {} catch {}
        } else if (op == 8) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            address caller = (s >> 16) % 2 == 0 ? o : address(noop);
            vm.prank(caller);
            try vault.transform(tid, address(noop), "") {} catch {}
        } else {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            vm.prank(o);
            try vault.transferLoan(tid, makeAddr("dst")) {} catch {}
        }
    }

    function _mk(uint128 liq) external returns (uint256 tid) {
        tid = _createLoan(liq);
    }

    function _owner(uint256 tid) internal view returns (bool, address) {
        try vault.ownerOf(tid) returns (address cur) { return (true, cur); }
        catch { return (false, address(0)); }
    }

    function _track(uint256 tid) internal {
        if (!seen[tid]) { seen[tid] = true; known.push(tid); }
    }

    function _checkP2(uint256 step) internal view {
        uint256 sum;
        for (uint256 i; i < known.length; i++) sum += vault.loans(known[i]);
        assertTrue(vault.debtSharesTotal() == sum, string(abi.encodePacked("P2 BROKEN step ", _n(step))));
    }

    function _n(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        bytes memory b;
        while (v > 0) { b = bytes.concat(bytes1(uint8(48 + (v % 10))), b); v /= 10; }
        return string(b);
    }
}

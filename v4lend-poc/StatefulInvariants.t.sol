// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.30;

import {V4VaultLocalBase} from "test/vault/support/V4VaultLocalBase.sol";
import {IVault} from "src/vault/interfaces/IVault.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

/// @notice No-op transformer: any call succeeds, moves nothing.
contract NoopTransformerSI {
    fallback() external {}
}

/// @notice Stateful invariant sweep over V4Vault core lifecycle.
/// P1 (solvency): every loan with debtShares > 0 has collateralValue >= debt.
///   (Necessary condition: healthy loans need debt <= factor*collateral < collateral,
///   so collateral < debt means definite insolvency -> High-grade signal.)
/// P2 (conservation): debtSharesTotal == sum(loans[i].debtShares) over all known tokens.
/// Ops (seed-driven, all try/catch): create / borrow / repay / approve+transform /
/// remove / re-create / transferLoan / liquidate-attempt / warp.
/// Run: forge test --match-contract StatefulInvariants -vvv
contract StatefulInvariants is V4VaultLocalBase {
    NoopTransformerSI internal noop;
    address internal operator = makeAddr("operator");
    address internal other = makeAddr("other");

    uint256[] internal known;
    mapping(uint256 => bool) internal seen;

    function setUp() public override {
        super.setUp();
        noop = new NoopTransformerSI();
        vault.setTransformer(address(noop), true);
        _deposit(lender, 1_000_000 ether);
    }

    function test_stateful(uint256 seed) public {
        uint256 s = seed == 0 ? 1 : seed;
        for (uint256 step; step < 48; step++) {
            s = uint256(keccak256(abi.encode(s, step)));
            _step(s, step);
            _checkP1P2(step);
        }
        assertTrue(vault.transformedTokenId() == 0, "mutex stuck");
    }

    function _step(uint256 s, uint256 step) internal {
        uint256 op = s % 10;
        if (op == 0) {
            uint128 liq = uint128(1e10 + (s >> 8) % 1e12);
            uint256 tid = _createLoan(liq);
            _track(tid);
        } else if (op == 1) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool ok, address o) = _owner(tid);
            if (!ok) return;
            (, uint256 fullValue,,,) = vault.loanInfo(tid);
            if (fullValue == 0) return;
            uint256 amt = fullValue / 3 + ((s >> 16) % (fullValue / 3 + 1));
            vm.prank(o);
            try vault.borrow(tid, amt) {} catch {}
        } else if (op == 2) {
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
        } else if (op == 3) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            vm.prank(o);
            try vault.approveTransform(tid, operator, (s >> 16) % 2 == 0) {} catch {}
        } else if (op == 4) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            address caller = (s >> 16) % 2 == 0 ? o : operator;
            vm.prank(caller);
            try vault.transform(tid, address(noop), "") {} catch {}
        } else if (op == 5) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (bool okO, address o) = _owner(tid);
            if (!okO) return;
            vm.prank(o);
            try vault.remove(tid, o, "") {} catch {}
        } else if (op == 6) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            // re-create only makes sense for a token the vault no longer holds as a loan;
            // attempt anyway, try/catch filters.
            address o = borrower;
            try vault.ownerOf(tid) returns (address cur) {
                o = cur;
            } catch {}
            vm.startPrank(o);
            try IERC721(address(positionManager)).approve(address(vault), tid) {
                try vault.create(tid, o) {} catch {}
            } catch {}
            vm.stopPrank();
        } else if (op == 7) {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            address o;
            try vault.ownerOf(tid) returns (address cur) {
                o = cur;
            } catch {
                return;
            }
            address dest = o == other ? borrower : other;
            vm.prank(o);
            try vault.transferLoan(tid, dest) {} catch {}
        } else if (op == 8) {
            vm.warp(block.timestamp + 1 hours + ((s >> 8) % 7 days));
        } else {
            if (known.length == 0) return;
            uint256 tid = known[(s >> 8) % known.length];
            (,,, uint256 cost,) = vault.loanInfo(tid);
            if (cost == 0) return;
            asset.mint(liquidator, cost);
            vm.startPrank(liquidator);
            asset.approve(address(vault), cost);
            try vault.liquidate(IVault.LiquidateParams(tid, 0, 0, liquidator, block.timestamp, "")) {} catch {}
            vm.stopPrank();
        }
        step; // silence
    }

    function _owner(uint256 tid) internal view returns (bool, address) {
        try vault.ownerOf(tid) returns (address cur) {
            return (true, cur);
        } catch {
            return (false, address(0));
        }
    }

    function _track(uint256 tid) internal {
        if (!seen[tid]) {
            seen[tid] = true;
            known.push(tid);
        }
    }

    function _checkP1P2(uint256 step) internal view {
        uint256 sum;
        for (uint256 i; i < known.length; i++) {
            uint256 tid = known[i];
            uint256 sh = vault.loans(tid);
            sum += sh;
            if (sh > 0) {
                (uint256 debt, uint256 fullValue, uint256 collateralValue,,) = vault.loanInfo(tid);
                fullValue;
                assertTrue(
                    collateralValue >= debt,
                    string(abi.encodePacked("P1 BROKEN step ", _n(step), " tid ", _n(tid)))
                );
            }
        }
        assertTrue(
            vault.debtSharesTotal() == sum,
            string(abi.encodePacked("P2 BROKEN step ", _n(step)))
        );
    }

    function _n(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        bytes memory b;
        while (v > 0) {
            b = bytes.concat(bytes1(uint8(48 + (v % 10))), b);
            v /= 10;
        }
        return string(b);
    }
}

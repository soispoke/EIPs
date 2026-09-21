#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Python 3 reference assembler for the EIP-8250 runtime at 0x8250."""
OP = {"STOP": 0x00, "EQ": 0x14, "ISZERO": 0x15, "SHR": 0x1c,
      "KECCAK256": 0x20, "ADDRESS": 0x30, "CALLER": 0x33,
      "CALLVALUE": 0x34, "CALLDATALOAD": 0x35, "CALLDATASIZE": 0x36,
      "MSTORE": 0x52, "SLOAD": 0x54, "SSTORE": 0x55, "JUMPI": 0x57,
      "JUMPDEST": 0x5b, "PUSH0": 0x5f, "DUP1": 0x80, "SWAP1": 0x90,
      "REVERT": 0xfd}

# A tuple is either PUSH(value, width), REF(label), or LABEL(label).
PROGRAM = [
    "ADDRESS", (0x8250, 2), "EQ", "ISZERO", ("ref", "fail"), "JUMPI",
    "CALLVALUE", ("ref", "fail"), "JUMPI",
    "CALLDATASIZE", (36, 1), "EQ", "ISZERO", ("ref", "fail"), "JUMPI",
    "PUSH0", "CALLDATALOAD", (224, 1), "SHR", (0xaf6f8c1b, 4), "EQ",
    "ISZERO", ("ref", "fail"), "JUMPI",
    (4, 1), "CALLDATALOAD", "DUP1", "ISZERO", ("ref", "fail"), "JUMPI",
    (32, 1), "MSTORE", "CALLER", "PUSH0", "MSTORE",
    (64, 1), "PUSH0", "KECCAK256", "DUP1", "SLOAD", ("ref", "fail"), "JUMPI",
    (1, 1), "SWAP1", "SSTORE", "STOP",
    ("label", "fail"), "JUMPDEST", "PUSH0", "PUSH0", "REVERT",
]


def assemble():
    code, labels, patches, listing = bytearray(), {}, [], []
    for insn in PROGRAM:
        pc = len(code)
        if isinstance(insn, str):
            code.append(OP[insn])
            desc = insn
        elif insn[0] == "label":
            assert insn[1] not in labels
            labels[insn[1]] = pc
            continue
        elif insn[0] == "ref":
            code.extend([0x60, 0])
            patches.append((pc + 1, insn[1]))
            desc = "PUSH1 " + insn[1]
        else:
            value, width = insn
            assert 1 <= width <= 32 and 0 <= value < 1 << (8 * width)
            code.append(0x5f + width)
            code.extend(value.to_bytes(width, "big"))
            desc = f"PUSH{width} 0x{value:0{2 * width}x}"
        listing.append((pc, len(code), desc))
    for at, label in patches:
        assert labels[label] < 256
        code[at] = labels[label]
    return bytes(code), "\n".join(
        f"{start:04x}  {bytes(code[start:end]).hex():<12} {desc}"
        for start, end, desc in listing) + "\n"



if __name__ == "__main__":
    print("0x" + assemble()[0].hex())

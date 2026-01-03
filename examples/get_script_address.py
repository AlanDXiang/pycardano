from pycardano import Address, ScriptHash, Network

# 1. Your script hash from Step 1 (hex string)
script_hash_hex = "1534828b3f28a816a421137fba569f855c2ffa3876649638e78a096c"

# 2. Convert hex string to ScriptHash object
script_hash = ScriptHash(bytes.fromhex(script_hash_hex))

# 3. Derive the address
# Use Network.TESTNET for addr_test... or Network.MAINNET for addr1...
script_address = Address(payment_part=script_hash, network=Network.TESTNET)

print(f"Derived Address: {script_address}")
# This will match Step 2: addr_test1wq2nfq5t8u52s94yyyfhlwjkn7z4ctl68pmxf93cu79qjmq2hd8h8
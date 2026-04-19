from eth_account import Account
import json

with open('config.json') as f:
    config = json.load(f)

sk = config['secret_key']
acct = Account.from_key(sk)
target = '0x7dd9f0C23Fb61CA3f36B8414306310F963093c12'

print(f'Secret Key: {sk}')
print(f'Derived Address: {acct.address}')
print(f'Target Address:  {target}')
print(f'Match: {acct.address.lower() == target.lower()}')

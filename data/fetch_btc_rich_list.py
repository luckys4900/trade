# -*- coding: utf-8 -*-
"""
BTC Top 100 Rich List Wallet Fetcher
Parses Bitinfocharts data to extract whale wallet addresses with metadata
"""

import json
import re
from datetime import datetime

RAW_DATA = """
134xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo wallet:Binance-coldwallet Balance:248598BTC Ins:5505 Outs:451 2018-10-18 2026-04-03
23M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6 wallet:Binance-coldwallet 7d:-6193BTC 30d:-10960BTC Balance:145066BTC Ins:481 Outs:292 2018-11-13 2026-03-31
bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2 wallet:Robinhood-coldwallet Balance:140575BTC Ins:509 Outs:439 2023-05-08 2026-04-07
bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97 wallet:Bitfinex-coldwallet Balance:130010BTC Ins:340 Outs:296 2019-08-16 2026-03-19
bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfc27a4 wallet:Tether 7d:+951.35BTC 30d:+955.35BTC Balance:97141BTC Ins:175 Outs:159 2022-09-30 2026-04-15
bc1qazcm763858nkj2dj986etajv6wquslv8uxwczt wallet:Bitfinex-Hack-Recovery Balance:94643BTC Ins:179 Outs:0 2022-02-01 2026-03-31
bc1qd4ysezhmypwty5dnw7c8nqy5h5nxg0xqsvaefd0qn5kq32vwnwqqgv4rzr Balance:91850BTC Ins:197 Outs:176 2021-10-11 2026-04-18
1FeexV6bAHb8ybZjqQMjJrcCrHGW9sb6uF wallet:MtGox-Hack Balance:79957BTC Ins:678 Outs:0 2011-03-01 2026-04-07
bc1q8yj0herd4r4yxszw3nkfvt53433thk0f5qst4g Balance:78317BTC Ins:79 Outs:0 2024-03-23 2026-03-24
1Ay8vMC7R1UbyCCZRVULMV7iQpHSAbguJP wallet:Mr.100 7d:+87.96BTC 30d:+1750BTC Balance:71410BTC Ins:2406 Outs:811 2022-11-02 2026-04-19
bc1qa5wkgaew2dkv56kfvj49j0av5nml45x9ek9hz6 wallet:SilkRoad-FBI-Confiscated Balance:69370BTC Ins:162 Outs:0 2020-11-03 2026-03-31
3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb wallet:Binance-BTCB-Reserve Balance:68200BTC Ins:153 Outs:54 2019-06-17 2026-03-24
bc1q0ymzksy046tv4z88ts5nmu7s574umnwmdev3rt Balance:60658BTC Ins:45 Outs:1 2025-08-20 2026-04-18
3MgEAFWu1HKSnZ5ZsC8qf61ZW18xrP5pgd wallet:OKEx 30d:-500BTC Balance:55905BTC Ins:733 Outs:442 2022-12-16 2026-04-16
1LdRcdxfbSnmCYYNdeYpUnztiYzVfBEQeC Balance:53880BTC Ins:247 Outs:0 2014-05-27 2026-03-24
1AC4fMwgY8j9onSbXEWeH6Zan8QGMSdmtA Balance:51830BTC Ins:159 Outs:0 2018-01-07 2026-01-29
1LruNZjwamWJXThX2Y8C2d47QqhAkkc5os Balance:44000BTC Ins:105 Outs:0 2019-11-24 2026-03-24
bc1q4j7fcl8zx5yl56j00nkqez9zf3f6ggqchwzzcs5hjxwqhsgxvavq3qfgpr wallet:Coincheck 7d:-3.38BTC 30d:-123.39BTC Balance:42315BTC Ins:3044 Outs:2931 2024-02-02 2026-04-18
bc1qhk0ghcywv0mlmcmz408sdaxudxuk9tvng9xx8g wallet:92995586 7d:-1620BTC 30d:-925BTC Balance:41858BTC Ins:691 Outs:622 2022-07-20 2026-04-14
bc1qa2eu6p5rl9255e3xz7fcgm6snn4wl5kdfh7zpt05qp5fad9dmsys0qjg0e 7d:-3000BTC 30d:-3000BTC Balance:41194BTC Ins:74 Outs:23 2024-06-30 2026-04-16
bc1qws342rlkhszh58rtn35zrw7w076puz83gkcufy 30d:-1198BTC Balance:41075BTC Ins:92 Outs:91 2025-09-23 2026-04-11
3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a wallet:Binance-coldwallet Balance:37927BTC Ins:79 Outs:0 2021-10-24 2026-03-24
bc1q7ydrtdn8z62xhslqyqtyt38mm4e2c4h3mxjkug wallet:UK-Gov-Confiscated Balance:36000BTC Ins:83 Outs:0 2021-07-27 2026-03-24
bc1qukw69mjxwp30adfqddv6gcyva26laxz562rhlk 7d:+991.4BTC 30d:+2424BTC Balance:35040BTC Ins:23 Outs:3 2025-08-20 2026-04-14
bc1qx9t2l3pyny2spqpqlye8svce70nppwtaxwdrp4 wallet:Binance-Pool Balance:31643BTC Ins:4804 Outs:1 2020-05-12 2026-03-28
3FuhQLprN9s9MR3bZzR5da7mw75fuahsaU 7d:+510.14BTC 30d:-4.7BTC Balance:31638BTC Ins:2806 Outs:390 2024-11-22 2026-04-19
bc1qy3uw2kk45uj9vsy52rjfhydm2tnd6hreu8vha3 Balance:31484BTC Ins:33 Outs:8 2025-08-19 2026-03-04
3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B wallet:Binance-coldwallet Balance:31275BTC Ins:75 Outs:0 2021-07-26 2026-03-24
12ib7dApVFvg82TXKycWBNpN8kFyiAN1dr wallet:967 Balance:31000BTC Ins:250 Outs:4 2010-05-13 2026-04-10
bc1q8taf2eca7pn9wu4czt8fgftqm288xtfxdyt33syzxuexxty733xsszghzk Balance:30800BTC Ins:23 Outs:15 2024-12-31 2026-03-04
bc1q6h2v33qt0jjvpr2hxxtwhtvdvtn086g0n2qu06 30d:-408BTC Balance:30574BTC Ins:24 Outs:13 2025-11-05 2026-03-24
12tkqA9xSoowkzoERHMWNKsTey55YEBqkv Balance:28151BTC Ins:212 Outs:0 2010-04-05 2026-03-24
3EMVdMehEq5SFipQ5UfbsfMsH223sSz9A9 4-of-8 Balance:26984BTC Ins:113 Outs:79 2019-02-01 2026-03-24
3FsDiWdG76meMpdCLbVV4dUXhrFyaLrtxL Balance:26916BTC Ins:3 Outs:0 2026-01-10 2026-02-09
39eYrpgAgDhp4tTjrSb1ppZ5kdAc1ikBYw Balance:26062BTC Ins:42 Outs:3 2023-12-07 2026-03-24
bc1qysj2w7xsw09datsy9mt9x50jn7qjd6qde6d66qm3ce0a4y9uzdqcavdr0 7d:-125BTC 30d:+63.97BTC Balance:25245BTC Ins:99 Outs:46 2025-03-25 2026-04-15
1N7jWmv63mkMdsYzbNUVHbEYDQfcq1u8Yp Balance:24052BTC Ins:8 Outs:0 2024-12-05 2026-02-09
15cHRgVrGKz7qp2JL2N5mkB2MCFGLcnHxv Balance:23600BTC Ins:84 Outs:4 2022-06-16 2026-04-15
bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9 wallet:Crypto.com-coldwallet 7d:+2424BTC 30d:+2773BTC Balance:21645BTC Ins:89003 Outs:86422 2022-03-04 2026-04-19
bc1qs4z2d3h5je080f74tax92dwg08sf3hylj9vfg3 30d:+2750BTC Balance:20755BTC Ins:18 Outs:12 2026-01-22 2026-04-15
bc1qcpflj68s3ahy4xajez4d8v3vk28pvf7qte2jmlftvxzfke2u6mqsge3gvh 7d:-5146BTC 30d:-7406BTC Balance:20337BTC Ins:363 Outs:362 2024-03-01 2026-04-16
bc1qx2x5cqhymfcnjtg902ky6u5t5htmt7fvqztdsm028hkrvxcl4t2sjtpd9l wallet:Bitbank-coldwallet 7d:+5.59BTC 30d:+67.87BTC Balance:20230BTC Ins:8018 Outs:7965 2022-07-22 2026-04-19
17rm2dvb439dZqyMe2d4D6AQJSgg6yeNRn Balance:20008BTC Ins:118 Outs:1 2017-03-28 2026-03-24
1PeizMg76Cf96nUQrYg8xuoZWLQozU5zGW Balance:19414BTC Ins:151 Outs:0 2010-07-24 2026-03-24
bc1q72nyp6mzxjxm02j7t85pg0pq24684zdj2wuweu 7d:-9BTC 30d:-98BTC Balance:19125BTC Ins:36 Outs:35 2024-12-30 2026-04-13
bc1p6mv2d3rpfhatkv77r6huuurgqyyklxpsnw3090k2qjwqtd6cwkcqzsruxt 30d:+16500BTC Balance:16500BTC Ins:35 Outs:0 2026-03-15 2026-04-15
bc1qptc9cz269u2mc5yguun5a5d6yd5c7f7ne4qj26 Balance:16400BTC Ins:4 Outs:0 2025-12-15 2026-02-09
34HpHYiyQwg69gFmCq2BGHjF1DZnZnBeBP wallet:Binance-coldwallet Balance:16307BTC Ins:61 Outs:0 2021-10-22 2026-04-03
38rFtDdFpXc4y6XPbSnNd2UvveEt5Xms2E Balance:16116BTC Ins:4 Outs:0 2025-12-08 2026-02-09
3GPAWK5aUB5Ve9akvTzZgp69USjgbhFbay 2-of-3 wallet:78163677 7d:+125.89BTC 30d:+829.13BTC Balance:15818BTC Ins:1216 Outs:988 2021-04-07 2026-04-17
1GR9qNz7zgtaW5HwwVpEJWMnGWhsbsieCG Balance:15746BTC Ins:109 Outs:1 2018-01-22 2026-03-26
3FM9vDYsN2iuMPKWjAcqgyahdwdrUxhbJ3 wallet:OKEx 7d:+120.2BTC 30d:-155.55BTC Balance:15612BTC Ins:393 Outs:277 2024-01-05 2026-04-18
1BAuq7Vho2CEkVkUxbfU26LhwQjbCmWQkD Balance:15000BTC Ins:27 Outs:5 2022-01-29 2026-04-16
1PJiGp2yDLvUgqeBsuZVCBADArNsk6XEiw wallet:Binance-coldwallet 7d:+379BTC 30d:+379BTC Balance:14605BTC Ins:177 Outs:66 2023-12-21 2026-04-14
bc1qlt5nm3kflne7rht4alsnzdzad878ld5rcu4na0 7d:+127.27BTC 30d:+151.38BTC Balance:14277BTC Ins:42076 Outs:22910 2024-10-14 2026-04-19
1CNtkWbb4grh8xtb8mhoZ6armNE9PHgzA8 30d:-15.3BTC Balance:13837BTC Ins:152 Outs:14 2023-01-13 2026-03-26
3KZbyboy2MKfQjDKKf2R4UdVbUKgYvso22 7d:-4000BTC 30d:-7000BTC Balance:13589BTC Ins:4 Outs:3 2026-03-16 2026-04-17
bc1qsg6x2cvm75xuddn5g0ss9zglaamgz90q8vcp8w Balance:13514BTC Ins:6 Outs:1 2025-08-29 2026-01-05
bc1qvrwzs8unvu35kcred2z5ujjef36s5jgf3y6tp8 Balance:13108BTC Ins:29 Outs:0 2025-10-15 2025-12-22
bc1q4vxn43l44h30nkluqfxd9eckf45vr2awz38lwa wallet:UK-Gov-Confiscated Balance:13003BTC Ins:48 Outs:0 2021-07-27 2026-03-20
36X44rmLtk218sXACZ3gFpNMFENi6dQ2n3 7d:+115.54BTC 30d:+12554BTC Balance:12554BTC Ins:33 Outs:9 2026-03-30 2026-04-17
bc1p4zxtwg3rhr5jqkzuvf0q03m2a69clydghqqz6arhldxln7ew0guq840aqm 30d:+12500BTC Balance:12500BTC Ins:27 Outs:0 2026-03-15 2026-04-15
39gUvGynQ7Re3i15G3J2gp9DEB9LnLFPMN Balance:12477BTC Ins:454 Outs:343 2021-02-24 2026-03-24
bc1qkmk4v2xn29yge68fq6zh7gvfdqrvpq3v3p3y0s wallet:Bitfinex-Hack-Recovery Balance:12267BTC Ins:31 Outs:0 2024-02-28 2026-03-26
bc1qchctnvmdva5z9vrpxkkxck64v7nmzdtyxsrq64 wallet:BitMEX 7d:-361.55BTC 30d:-196.66BTC Balance:12189BTC Ins:909 Outs:908 2023-10-31 2026-04-18
1Pzaqw98PeRfyHypfqyEgg5yycJRsENrE7 wallet:Binance-coldwallet 7d:-266BTC 30d:-218BTC Balance:11010BTC Ins:283 Outs:214 2023-06-19 2026-04-17
bc1qatjx2qc8vxz39m0qdz303z8et2pgmc74xz8km3 7d:-9.98BTC 30d:-307.85BTC Balance:10991BTC Ins:114 Outs:113 2024-12-30 2026-04-17
1F34duy2eeMz5mSrvFepVzy7Y1rBsnAyWC Balance:10771BTC Ins:130 Outs:0 2011-08-08 2026-03-26
bc1qxlth5har0qasqvattsjvgp80st2x402u5shuud Balance:10500BTC Ins:15 Outs:0 2024-06-22 2026-04-05
1ANkDML9LtVv1E1EF7cwPFEkSv6Bpojwyt Balance:10423BTC Ins:3 Outs:0 2025-11-18 2026-02-09
3NWndKFmvV6cJ6ENgXVeaDTo3mBfAvr27H 3-of-8 7d:+47.11BTC 30d:+86.93BTC Balance:10326BTC Ins:3837 Outs:3713 2019-02-01 2026-04-17
19dNe9Xg6JWvszgU3NuM6TNd2wHmANPbHB Balance:10265BTC Ins:34 Outs:26 2024-01-09 2026-03-18
1Q8QR5k32hexiMQnRgkJ6fmmjn5fMWhdv9 wallet:Binance-Pool Balance:10217BTC Ins:1629 Outs:0 2021-08-12 2026-03-26
bc1qsxdxm0exqdsmnl9ejrz250xqxrxpxkgf5nhhtq Balance:10002BTC Ins:48 Outs:0 2021-08-14 2026-03-26
1Ki3WTEEqTLPNsN5cGTsMkL2sJ4m5mdCXT Balance:10000BTC Ins:73 Outs:0 2017-10-16 2026-03-26
1DzsfLRDfbmQM99xm59au2SrTY3YmciBSB Balance:10000BTC Ins:37 Outs:1 2022-11-02 2026-03-26
1GUfWdZQoo2pQ4BKHsiegxuZPnheY5ueTm Balance:10000BTC Ins:28 Outs:1 2022-11-02 2026-03-26
12HnxiXEeKUVjQRbMVTytsGWnzHd5LdGCt Balance:10000BTC Ins:28 Outs:1 2022-11-02 2026-03-20
17uULjz9moeLyjXHoKNwDRgKzf8ahY3Jia Balance:10000BTC Ins:28 Outs:1 2022-11-02 2026-03-26
18qNs1yBGGKR8RyErnEF5kegbNUgPfixhS Balance:10000BTC Ins:30 Outs:1 2022-11-02 2026-03-26
1DP3VYwN6ozHXDDaETbvNFLd86CAXfaewi Balance:10000BTC Ins:39 Outs:1 2022-11-02 2026-04-16
1NhJGUJu8rrTwPS4vopsdTqqcK4nAwdLwJ Balance:10000BTC Ins:32 Outs:1 2022-11-02 2026-03-26
1MtUMTqtdrpT6Rar5fgWoyrzAevatssej5 Balance:10000BTC Ins:31 Outs:1 2022-11-02 2026-03-26
1MewpRkpcbFdqamPPYc1bXa9AJ189Succy Balance:10000BTC Ins:26 Outs:1 2022-11-02 2026-02-25
1H2MXWiSniAgg7ykdXEzPHL6oTH1ic4kP Balance:10000BTC Ins:39 Outs:1 2022-11-02 2026-04-16
1CY7fykRLWXeSbKB885Kr4KjQxmDdvW923 wallet:OKX Balance:10000BTC Ins:59 Outs:0 2020-01-18 2026-04-09
bc1qxkhwkn623l5lg4rx9vx8cujmleaga0eg6wc7p6 Balance:9800BTC Ins:10 Outs:0 2024-12-02 2026-02-08
bc1q9d5lq9psmkx9rtgewjgez7csg45faak2cccew8 Balance:9725BTC Ins:18 Outs:2 2025-04-01 2026-02-09
bc1qd46j77pkp5vdxraf8tw5l6xs36dlygdx2rt9ly Balance:9500BTC Ins:17 Outs:0 2024-06-27 2025-12-22
162bzZT2hJfv5Gm3ZmWfWfHJjCtMD6rHhw wallet:gate.io-coldwallet 7d:-965.8BTC 30d:-987.96BTC Balance:9460BTC Ins:1197 Outs:746 2022-10-19 2026-04-19
1P9fAFAsSLRmMu2P7wZ5CXDPRfLSWTy9N8 Balance:9425BTC Ins:63 Outs:0 2017-10-15 2026-04-06
17MWdxfjPYP2PYhdy885QtihfbW181r1rn Balance:9343BTC Ins:63 Outs:4 2020-12-13 2026-03-24
13uZyaPbt4rTwYQ8xWFySVUzWH3pk2P5c7 wallet:84890554 7d:-91.74BTC 30d:+666.1BTC Balance:9310BTC Ins:2684 Outs:2642 2022-02-15 2026-04-05
1HLvaTs3zR3oev9ya7Pzp3GB9Gqfg6XYJT Balance:9260BTC Ins:113 Outs:0 2010-03-18 2026-02-27
33eU1zeB2S4x3p4ccSsnAChXcGJgtMrMtZ wallet:82375777 Balance:9252BTC Ins:51 Outs:6 2019-10-07 2026-02-26
bc1qukqenm2t85dhdta9glqehllglxznsu4qyxn079 Balance:9112BTC Ins:9 Outs:0 2024-07-05 2025-12-22
bc1qffyax9rrxmqyq8xwjkzrrqwqjp3ppz5a4665f9 Balance:9099BTC Ins:10 Outs:0 2024-07-09 2026-02-09
bc1p77rtrsvsrl5nhu44hg7jp5hkz24qx044jgswx7sejpuwqckqcxxq5ejgvr 7d:+6124BTC 30d:+9039BTC Balance:9039BTC Ins:22 Outs:0 2026-03-16 2026-04-17
167ZWTT8n6s4ya8cGjqNNQjDwDGY31vmHg Balance:8999BTC Ins:78 Outs:0 2010-08-09 2026-02-20
1LVYbnSX6f6vE2Zn4zs2oZ4eKyBgzkqaay 30d:+301BTC Balance:8647BTC Ins:92 Outs:1 2022-11-30 2026-04-10
"""

EXCHANGE_LABELS = {
    "Binance-coldwallet": "exchange",
    "Binance-BTCB-Reserve": "exchange",
    "Binance-Pool": "exchange",
    "Robinhood-coldwallet": "exchange",
    "Bitfinex-coldwallet": "exchange",
    "Bitfinex-Hack-Recovery": "hack_recovery",
    "Tether": "stablecoin_issuer",
    "MtGox-Hack": "hack_recovery",
    "SilkRoad-FBI-Confiscated": "gov_seized",
    "UK-Gov-Confiscated": "gov_seized",
    "OKEx": "exchange",
    "OKX": "exchange",
    "Coincheck": "exchange",
    "Crypto.com-coldwallet": "exchange",
    "Bitbank-coldwallet": "exchange",
    "BitMEX": "exchange",
    "gate.io-coldwallet": "exchange",
    "Mr.100": "unknown_whale",
}

KNOWN_EXCHANGE_ADDRESSES = {
    "134xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance",
    "23M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6": "Binance",
    "3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a": "Binance",
    "3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B": "Binance",
    "34HpHYiyQwg69gFmCq2BGHjF1DZnZnBeBP": "Binance",
    "1PJiGp2yDLvUgqeBsuZVCBADArNsk6XEiw": "Binance",
    "1Pzaqw98PeRfyHypfqyEgg5yycJRsENrE7": "Binance",
    "1Q8QR5k32hexiMQnRgkJ6fmmjn5fMWhdv9": "Binance",
    "bc1qx9t2l3pyny2spqpqlye8svce70nppwtaxwdrp4": "Binance",
    "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2": "Robinhood",
    "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97": "Bitfinex",
    "3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb": "Binance",
    "3MgEAFWu1HKSnZ5ZsC8qf61ZW18xrP5pgd": "OKEx",
    "3FM9vDYsN2iuMPKWjAcqgyahdwdrUxhbJ3": "OKEx",
    "1CY7fykRLWXeSbKB885Kr4KjQxmDdvW923": "OKX",
    "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9": "Crypto.com",
    "bc1qx2x5cqhymfcnjtg902ky6u5t5htmt7fvqztdsm028hkrvxcl4t2sjtpd9l": "Bitbank",
    "bc1qchctnvmdva5z9vrpxkkxck64v7nmzdtyxsrq64": "BitMEX",
    "162bzZT2hJfv5Gm3ZmWfWfHJjCtMD6rHhw": "gate.io",
    "bc1q4j7fcl8zx5yl56j00nkqez9zf3f6ggqchwzzcs5hjxwqhsgxvavq3qfgpr": "Coincheck",
}

EXCHANGE_WALLET_ADDRESSES = {
    "Binance": [
        "134xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
        "23M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6",
        "3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a",
        "3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B",
        "34HpHYiyQwg69gFmCq2BGHjF1DZnZnBeBP",
        "1PJiGp2yDLvUgqeBsuZVCBADArNsk6XEiw",
        "1Pzaqw98PeRfyHypfqyEgg5yycJRsENrE7",
        "1Q8QR5k32hexiMQnRgkJ6fmmjn5fMWhdv9",
        "bc1qx9t2l3pyny2spqpqlye8svce70nppwtaxwdrp4",
    ],
    "Robinhood": [
        "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2",
    ],
    "Bitfinex": [
        "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
    ],
    "OKEx": [
        "3MgEAFWu1HKSnZ5ZsC8qf61ZW18xrP5pgd",
        "3FM9vDYsN2iuMPKWjAcqgyahdwdrUxhbJ3",
    ],
    "OKX": [
        "1CY7fykRLWXeSbKB885Kr4KjQxmDdvW923",
    ],
    "Crypto.com": [
        "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9",
    ],
    "Bitbank": [
        "bc1qx2x5cqhymfcnjtg902ky6u5t5htmt7fvqztdsm028hkrvxcl4t2sjtpd9l",
    ],
    "BitMEX": [
        "bc1qchctnvmdva5z9vrpxkkxck64v7nmzdtyxsrq64",
    ],
    "gate.io": [
        "162bzZT2hJfv5Gm3ZmWfWfHJjCtMD6rHhw",
    ],
    "Coincheck": [
        "bc1q4j7fcl8zx5yl56j00nkqez9zf3f6ggqchwzzcs5hjxwqhsgxvavq3qfgpr",
    ],
    "Tether": [
        "bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfc27a4",
    ],
}


def parse_rich_list():
    wallets = []
    for line in RAW_DATA.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        addr_match = re.match(r'^([13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{39,59})', line)
        if not addr_match:
            continue
        address = addr_match.group(1)

        bal_match = re.search(r'Balance:(\d+)BTC', line)
        balance = int(bal_match.group(1)) if bal_match else 0

        label = "unknown"
        for key, val in EXCHANGE_LABELS.items():
            if key in line:
                label = val
                break

        exchange = KNOWN_EXCHANGE_ADDRESSES.get(address)

        d7_match = re.search(r'7d:([+-]?[\d.]+)BTC', line)
        d30_match = re.search(r'30d:([+-]?[\d.]+)BTC', line)
        d7 = float(d7_match.group(1)) if d7_match else 0.0
        d30 = float(d30_match.group(1)) if d30_match else 0.0

        ins_match = re.search(r'Ins:(\d+)', line)
        outs_match = re.search(r'Outs:(\d+)', line)
        ins = int(ins_match.group(1)) if ins_match else 0
        outs = int(outs_match.group(1)) if outs_match else 0

        wallets.append({
            "address": address,
            "balance_btc": balance,
            "label": label,
            "exchange": exchange,
            "change_7d_btc": d7,
            "change_30d_btc": d30,
            "total_ins": ins,
            "total_outs": outs,
            "is_exchange_inflow_target": exchange is not None and label == "exchange",
        })

    wallets.sort(key=lambda w: w["balance_btc"], reverse=True)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "bitinfocharts.com Top 100 Rich List",
        "total_wallets": len(wallets),
        "summary": {
            "exchange_wallets": len([w for w in wallets if w["exchange"]]),
            "gov_seized": len([w for w in wallets if w["label"] == "gov_seized"]),
            "hack_recovery": len([w for w in wallets if w["label"] == "hack_recovery"]),
            "unknown_whales": len([w for w in wallets if w["label"] in ("unknown", "unknown_whale")]),
            "stablecoin_issuer": len([w for w in wallets if w["label"] == "stablecoin_issuer"]),
        },
        "exchange_inflow_targets": EXCHANGE_WALLET_ADDRESSES,
        "wallets": wallets,
    }
    return result


if __name__ == "__main__":
    data = parse_rich_list()
    out_path = "data/btc_top100_whale_wallets.json"
    import os
    os.makedirs("data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {data['total_wallets']} wallets to {out_path}")
    print(f"\n=== Summary ===")
    for k, v in data["summary"].items():
        print(f"  {k}: {v}")
    print(f"\nExchange inflow targets: {sum(len(v) for v in EXCHANGE_WALLET_ADDRESSES.values())} addresses across {len(EXCHANGE_WALLET_ADDRESSES)} exchanges")
    print(f"\nTop 10 non-exchange whales (monitor for inflow):")
    non_ex = [w for w in data["wallets"] if not w["exchange"]]
    for w in non_ex[:10]:
        print(f"  {w['address'][:20]}... | {w['balance_btc']:>8,} BTC | {w['label']}")

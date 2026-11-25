# Moyik 公开存证日志 · Moyik public notary log

这是 [Moyik](https://moyik.com) 存证记录的公开部分的一份副本，每天自动更新四次。任何人都可以把它整份拷走，自己保存一份镜像。

This is a copy of the public part of [Moyik](https://moyik.com)'s notary records, refreshed four times a day. Anyone may copy the whole of it and keep a mirror of their own.

## 这里有什么 · What is here

| 路径 Path | 内容 Content |
|---|---|
| `checkpoints/` | 每一批封存的摘要：编号、指纹、上一批的指纹、Moyik 的签名。One file per checkpoint: number, fingerprints, the previous checkpoint's fingerprint, Moyik's signature |
| `anchors/` | 比特币时间证明（OpenTimestamps 的 `.ots` 文件）和它对应的原文。Bitcoin timestamp proofs (OpenTimestamps `.ots` files) and the text each one covers |
| `keys.json` | Moyik 用过的全部签名公钥。Every public key Moyik has signed with |
| `SPEC.md` | 格式说明，照着它可以自己写核验程序。The format, enough to write your own checker |
| `mirror.py` | 拷贝并检查这份日志的小程序，只需要 Python。The script that copies and checks the log; needs only Python |

这里没有任何空间、任何人的信息，只有指纹、数量和签名。

Nothing here says anything about any space or person: fingerprints, counts and signatures only.

## 它有什么用 · What it is for

Moyik 把空间里的关键节点（例如一次拍板）记成存证，每一批存证的指纹都串在上一批后面，并定期把最新的指纹写进比特币区块。这份公开日志让这串指纹留在 Moyik 之外：

- 历史一旦被改写，就和这里已经存下的副本对不上，`mirror.py` 会立刻报出是第几批。
- Moyik 的网站打不开，甚至 Moyik 不在了，这份日志和你手里的回执照样能核对。

Moyik records key moments in a space (a decision, for example) as notary entries. Each checkpoint's fingerprint is chained to the one before it, and the newest fingerprint is regularly anchored in a Bitcoin block. This log keeps that chain outside Moyik:

- If history is ever rewritten, it no longer matches the copies saved here, and `mirror.py` names the checkpoint.
- If Moyik's site is unreachable, or Moyik is gone, this log and the receipts in your hands can still be checked.

## 自己保存一份镜像 · Keep your own mirror

```
git clone https://github.com/sanqian30006688/moyik-notary-log
cd moyik-notary-log
python3 mirror.py              # 从 moyik.com 拷贝最新的并检查 · copy the newest from moyik.com and check
python3 mirror.py --check-only # 不联网，只检查已有的文件 · offline: check the files already here
```

想核对签名，先 `pip install cryptography`；不装也能检查指纹是否前后相接。一年的数据大约几十兆。

To check signatures as well, `pip install cryptography` first; without it the chain of fingerprints is still checked. A year of data is a few tens of megabytes.

镜像不需要任何人许可，也不需要被信任：每一批都带签名，并且能对到比特币区块上，保存镜像的人改不了它。

A mirror needs nobody's permission and does not need to be trusted: every checkpoint is signed and leads to a Bitcoin block, so whoever keeps a mirror cannot alter it.

## 核对比特币时间 · Check the Bitcoin time

用官方的 [OpenTimestamps 客户端](https://opentimestamps.org)，不经过 Moyik：

With the official [OpenTimestamps client](https://opentimestamps.org), without Moyik:

```
cd anchors
ots verify moyik-checkpoint-<n>.txt.ots
```

因为每一批都接在上一批后面，一批被写进区块，它之前的所有批次也就都有了时间证明。

Checkpoints are chained, so one anchored checkpoint covers every checkpoint before it.

## 它能证明什么，不能证明什么 · What it proves and what it does not

它能证明：记录在某个时间之前已经存在，之后没有被改过，并且由 Moyik 签过名。

它不能证明：记录的内容在写下那一刻是真的。

It proves that a record existed before a certain time, has not been changed since, and was signed by Moyik.

It does not prove that what was recorded was true when it was written.

## 核对你自己的回执 · Check your own receipt

空间成员可以在 Moyik 里导出某条存证的回执文件。回执自带核对所需的全部内容，步骤见 `SPEC.md` 的 “Checking a receipt without Moyik”。签名公钥请从这里的 `keys.json` 取，不要用回执里附带的那一份。

Members of a space can export a receipt for an entry in Moyik. A receipt carries everything needed to check it; the steps are in `SPEC.md` under "Checking a receipt without Moyik". Take the public key from `keys.json` here, not from the copy inside the receipt.

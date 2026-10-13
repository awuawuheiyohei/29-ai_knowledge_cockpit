# vault/

`questions.tar.age` — 加密归档,包含 `data/questions/` 全部 988 道题目。

## 里面是什么

从 ISACA 官方 CISSP 练习题 OCR 出的题目原文(题干、选项、解析、双语)。
这是**受版权保护的材料**,所以不能以明文进公开仓库。

## 怎么解开

```bash
./scripts/questions_vault.sh open      # 解密到 .vault-plaintext/
./scripts/questions_vault.sh verify    # 校验密文与本地目录一致
```

密钥在仓库外:`~/.secrets/knowledge-cockpit/questions.agekey`。
**这个密钥丢了,密文就永久无法还原** —— 请单独备份到别处。

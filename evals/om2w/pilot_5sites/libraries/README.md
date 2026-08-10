# Pilot primitive libraries

这里保存五站点 OM2W pilot 中通过 source WebJudge admission 后生成的原始 primitive catalog。

- `recreation_gov`：2 个 active primitives。
- `akc_org`：2 个 active primitives。
- `bbb_org`：1 个 active primitive。
- Healthline 和 The Weather Network 未达到至少两个 admitted source family 的建库门槛，
  因此没有 library。

每个 library 保持 Webwright 的运行时目录格式：

```text
<library-root>/.primitives/<site>/catalog.json
<library-root>/.primitives/<site>/code/*.py
```

这些文件是 pilot 的生成产物，不代表人工审核或生产级实现。具体来源、held-out 结果及 gate
未选择它们的原因见 [`../PILOT_REPORT.zh-CN.md`](../PILOT_REPORT.zh-CN.md)。

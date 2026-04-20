# GitHub README Logo Guidance

适用范围：

- GitHub 仓库首页 `README.md` 首屏 Logo
- 不涉及 README 正文改写

## 本次输入

- 源附件：`logo-横版-1024.png`
- 已入仓文件：
  - `assets/brand/qoreon-logo-horizontal-light.png`
  - `assets/brand/qoreon-logo-horizontal-dark.png`
- 规格：`1024 x 421`，PNG，透明背景

## 结论

### 1. 是否可直接用于 GitHub README 首屏

可以。

当前已补齐 `light + dark` 两个版本，适合 GitHub README 首屏按主题自动分流。

说明：

- `light` 版直接使用原始横版字标
- `dark` 版在原图基础上做了提亮处理，提升暗色主题下 `Qoreon` 字标对比度

### 2. 正式入仓文件名与路径

当前建议的正式文件为：

- `assets/brand/qoreon-logo-horizontal-light.png`
- `assets/brand/qoreon-logo-horizontal-dark.png`

命名理由：

- `horizontal` 明确这是 README / Hero 横版字标
- `light` 明确它是浅底优先版本
- 后续如果补暗底版，可直接配套：
  - `assets/brand/qoreon-logo-horizontal-dark.png`

### 3. 是否需要 light / dark 双版本

已补齐，当前推荐直接使用。

推荐优先级：

1. 当前方案：`light + dark` 双版本，README 用 HTML `picture`
2. 次优方案：只有浅底版时，用单文件 HTML `img`
3. 不建议：纯 Markdown 图片语法直接挂首屏

原因：

- Markdown 无法稳妥控制宽度、居中和暗色主题适配
- GitHub README 首屏是品牌位，不应把暗色主题可读性赌给浏览器缩放

### 4. 如果只保留单文件，最佳嵌入方式

推荐：

- 用 HTML `img`
- 建议宽度：`680` 到 `760`
- 默认推荐值：`720`

原因：

- `1024` 原图足够清晰
- `720` 在 GitHub README 首屏更接近官网 Hero 横版观感
- 比纯 Markdown 更容易控制首屏占比

推荐写法：

```html
<p align="center">
  <img
    src="assets/brand/qoreon-logo-horizontal-light.png"
    alt="Qoreon"
    width="720"
  />
</p>
```

## 如果补 dark 版后的推荐写法

```html
<p align="center">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="assets/brand/qoreon-logo-horizontal-dark.png"
    />
    <img
      src="assets/brand/qoreon-logo-horizontal-light.png"
      alt="Qoreon"
      width="720"
    />
  </picture>
</p>
```

## 对 README 文案线的兼容建议

- 首屏保留横版 Logo，不再复用方形头像图替代
- GitHub 首页仍应保留技术仓语义，Logo 下方要紧接一句定位和技术简介
- 横版 Logo 只负责品牌识别，不承担过多说明文字
- 现有 `assets/brand/qoreon-logo-primary.png` 继续保留给头像、小尺寸位和仓库社媒位

## 本轮不做的事

- 不替换现有头像图

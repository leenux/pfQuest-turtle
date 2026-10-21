# 中文端世界库汉化 SQL

日期：2026-10-21

为本地 MariaDB 世界库生成简体中文补丁。脚本只读数据库，只写 SQL 文件，不执行这些语句，也不改 pfQuest 的 lua 数据。

## 已定规则

需要补中文名的字段满足任一条件：值为 NULL、去掉首尾空白后为空、与英文名完全相同，或不含汉字。已含汉字的字段保持不动。

汉字指 U+4E00–U+9FFF 中的字符。字段里只要有一个这样的字符，就视为已有中文。

物品、法术、任务标题、NPC 的新中文名都来自 capycraft.io/db 上的同 ID 页面。页面上的名字必须含汉字，否则跳过。任务正文不从网站抓取。

NPC 对应 `locales_creature`。

## 数据流

脚本是 `toolbox/gen_cn_sql.py`。连接信息放在 `sql/db.local.json`，包含 `host`、`port`、`user`、`password`、`database`。默认主机 `127.0.0.1`，端口 `3306`。该文件和 `sql/cache/` 写入 `.gitignore`。

脚本对数据库只执行 `SELECT`。连不上库时停止，不写 SQL。

简体中文使用 MaNGOS 的 `loc4` 列，例如 `name_loc4`、`Title_loc4`。每个类别先从 `information_schema` 核对表和列。某一类的表或 `loc4` 列不存在时，跳过该类，不写该类的 SQL，并在跳过清单里说明；其他类继续。四类期望的表是：

- 物品：`item_template` 的英文名，`locales_item.name_loc4`
- 法术：`spell_template` 的英文名，`locales_spell.name_loc4`。这两张表缺一则跳过法术类
- 任务：`quest_template` 的英文标题和关联 ID，`locales_quest` 的 `loc4` 文本
- NPC：`creature_template` 的英文名，`locales_creature.name_loc4`

物品描述、法术描述、NPC 副标题不修改。

第 1 步只对需要补名的条目请求 capycraft。请求地址是 `https://capycraft.io/db/?{type}={id}`，`type` 分别为 `item`、`spell`、`quest`、`npc`。中文名取自页面 `<title>` 或主标题：从第一个汉字起，到下一处 ASCII 字母之前，再去掉首尾空白和分隔符。结果写入 `sql/cache/capycraft.json`，键为类别加 ID。同一缓存再跑时不再请求已经缓存的条目。

某一类的第一页如果 HTTP 成功但解析不到名称区域，停止该类的后续抓取，不改用别的 URL。这种结构性失败不计入下面的连续失败次数。

第 2 步不访问网站。正式名称优先用库里已有的中文名，否则用本次缓存里补上的中文名。正式名称仍不含汉字的，任务文本不动。

## 名称 SQL

本地化行不存在时写 `INSERT ... SELECT ... WHERE NOT EXISTS`，写入 `entry`、对应的 `loc4` 名称列，以及该表其他没有默认值的必填列（这些必填列写空字符串）。行已存在时写 `UPDATE`，`WHERE` 带上 entry 和生成时读到的原值（`IS NULL` 或等于当时的字符串）。文件重复执行时，已写成中文的行不再被改写。

四份文件都放在 `sql/`：

- `sql/spell-cn-2026-10-21.sql`
- `sql/item-cn-2026-10-21.sql`
- `sql/quest-cn-2026-10-21.sql`
- `sql/creature-2026-10-21.sql`

任务文件同时包含标题补名和下面的正文替换。文件编码为 UTF-8。字符串按 MariaDB 规则转义引号、反斜杠和换行。

## 任务正文

只改 `locales_quest` 里已经存在的 `loc4` 文本。涉及的列是 `Details_loc4`、`Objectives_loc4`、`ObjectiveText1_loc4` 到 `ObjectiveText4_loc4`、`OfferRewardText_loc4`、`RequestItemsText_loc4`、`EndText_loc4`。`loc4` 为空的正文不新造译文。

关联物品来自 `quest_template` 的 `ReqItemId1` 到 `ReqItemId4`，以及 `SrcItemId`。关联 NPC 来自 `ReqCreatureOrGOId1` 到 `ReqCreatureOrGOId4` 中大于 0 的值。小于或等于 0 的值是游戏对象或其他目标，不参与 NPC 替换。接任务、交任务 NPC 来自 `creature_questrelation` 和 `creature_involvedrelation`。这两张表不存在，或列名无法确定为生物 ID 加任务 ID 时，只使用 `ReqCreatureOrGOId`，并在跳过清单记录一次。

目标短句 `ObjectiveTextN_loc4` 只在第 N 个目标槽能对应到一个物品或一个 NPC 时整段替换。生物 ID 大于 0 时用该 NPC 的正式中文名；否则在物品 ID 大于 0 时用该物品的正式中文名。同一槽生物和物品都大于 0 时，不替换这一短句，并写入跳过清单。短句已经等于正式中文名时不动。正式中文名不含汉字时不动。

长文本只处理详情、目标、交接对话和结束文本。英文名按字符长度从长到短替换。长度少于 4 个字符的英文名不替换。长度达到 4 的英文名按数据库中的英文原样做大小写敏感匹配；两侧如果仍是 ASCII 字母，则不算出现，因此 `Wolf` 不会改掉 `Wolfsbane`。一处长文本里的全部匹配都替换。替换结果若成为空字符串，这条不写。

中文正文里使用了另一个中文别名，但其中没有可匹配的英文名时，保持原样。

正文 `UPDATE` 的 `WHERE` 包含 entry 和替换前的整段原文，重复执行不会再次改写。

## 失败处理

capycraft 单条打不开、返回 404，或解析结果不含汉字时，跳过该 ID，把类别、ID 和原因追加到 `sql/cn-2026-10-21-skipped.txt`，其他条目继续。各类别合计连续 20 次 HTTP 或解析失败后，停止后续所有抓取；已经写入缓存的名字仍然生成 SQL。

## 验证

用固定输入测试纯函数，不连接真实数据库，也不执行生成的 SQL。至少覆盖这些情况：

- 空值、与英文名相同、不含汉字的字段会生成写入；已含汉字的字段不生成
- capycraft 结果不含汉字时进入跳过清单，不生成写入
- 目标短句整段改为正式中文名；同一槽同时有生物和物品时不改
- 长文本中的英文名换成正式中文名；短于 4 个字符的不换；夹在更长英文单词中间的不换
- 正式名称仍是英文时，正文不变
- 中文别名且正文中没有英文名时，正文不变
- 较长的英文名先于较短的英文名替换
- 同一缓存再生成一次，四份 SQL 的内容相同

生成的每条名称语句都带防覆盖条件，每条正文语句都带原文条件。

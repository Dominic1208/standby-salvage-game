class_name Deal
extends RefCounted
## 一笔交易的全部规则：顾客性格、货物真实价值、鉴定、质疑来历、砍价。
## 不碰界面，方便以后写单元测试。数值来自 data/tuning.json，台词来自 data/personalities.json。

var tuning: Dictionary
var item: Dictionary          ## 本次生成的货物 {name, tag, base, art, leaky}
var customer: Dictionary      ## {name, type, art}
var persona: Dictionary       ## 性格数据（数值修正 + 台词池）
var rng: RandomNumberGenerator
var lying: bool
var story: String
var clues: Array = []         ## [{part, text, mult, revealed, is_lie}]
var true_value: int           ## 收购商日终真正会付的钱
var ask: int                  ## 顾客当前要价
var min_price: int            ## 顾客心里的底价（玩家看不到）
var patience: float
var rounds_left: int
var challenge_count := 0     ## 质疑过几次
var exposed := false          ## 谎言是否已被揭穿


## 创建一位新顾客：从货物库随机组合一件货（类别 + 成色 + 3 个检查部位），
## 从顾客原型里随机一位。reputation 越高，骗子越少。
func _init(p_tuning: Dictionary, catalog: Dictionary, archetypes: Array, personas: Dictionary,
		p_rng: RandomNumberGenerator, reputation: int) -> void:
	tuning = p_tuning
	rng = p_rng
	var arch: Dictionary = archetypes[rng.randi_range(0, archetypes.size() - 1)]
	customer = {"name": _pick(arch.names), "type": arch.type, "art": arch.art}
	persona = personas[customer.type]
	item = _make_item(catalog)

	var lie_chance := float(tuning.lie_chance) * float(persona.lie_mult) 		- reputation * float(tuning.rep_lie_reduction)
	lying = rng.randf() < clampf(lie_chance, 0.0, 0.9)
	var cat: Dictionary = catalog.categories[item.tag]
	var lie: Dictionary = _pick(cat.lies) if lying else {}
	if lying:
		story = lie.story
	elif rng.randf() < 0.45:
		story = _pick(catalog.meme_stories)
	else:
		story = _pick(cat.stories)

	# 抽 3 个检查部位；撒谎时一定包含谎言对应的部位
	var parts: Array = cat.parts.keys()
	parts.shuffle()
	parts = parts.slice(0, 3)
	if lying and not parts.has(lie.part):
		parts[rng.randi_range(0, 2)] = lie.part
	var value := float(item.base)
	for part in parts:
		var c := {"part": part, "revealed": false, "is_lie": false}
		if lying and part == lie.part:
			c["text"] = lie.text
			c["mult"] = 1.0
			c["is_lie"] = true
		else:
			var v: Array = _pick(cat.parts[part])
			c["text"] = v[0]
			c["mult"] = float(v[1])
			if v.size() > 2 and v[2] == "leaky":
				item["leaky"] = true
		value *= float(c.mult)
		clues.append(c)
	# 以“这个部位的平均结果”为基准：好线索让真实价值高于参考价，坏线索低于参考价。
	# 不除这个平均值的话，坏结果多的部位会把所有货物都系统性压低，玩家怎么出价都亏。
	for part in parts:
		value /= _mean_mult(cat.parts[part])
	if lying:
		value *= float(lie.mult)
	true_value = maxi(10, roundi(value * rng.randf_range(0.9, 1.1)))

	var greed := rng.randf_range(tuning.greed_min, tuning.greed_max) + float(persona.greed_add)
	ask = _round10(float(item.base) * greed)
	var floor_ratio := rng.randf_range(tuning.min_price_min, tuning.min_price_max) + float(persona.floor_add)
	if lying:
		floor_ratio *= float(tuning.liar_min_factor)
	min_price = mini(_round10(true_value * floor_ratio), ask)
	patience = float(tuning.patience_start) * float(persona.patience_mult)
	rounds_left = int(tuning.haggle_rounds)


## 从货物库组合一件货：{name, tag, base, art, leaky}
func _make_item(catalog: Dictionary) -> Dictionary:
	var row: Array = _pick(catalog.items)
	var cond: Array = _pick_weighted(catalog.conditions)
	return {
		"name": str(cond[0]) + str(row[0]),
		"tag": row[1],
		"base": maxi(10, roundi(float(row[2]) * float(cond[1]))),
		"art": catalog.categories[row[1]].art,
		"leaky": false,
	}


func _mean_mult(variants: Array) -> float:
	var total := 0.0
	for v in variants:
		total += float(v[1])
	return maxf(0.1, total / maxf(1.0, variants.size()))


func _pick(arr: Array) -> Variant:
	return arr[rng.randi_range(0, arr.size() - 1)]


## conditions 的每行是 [前缀, 倍数, 权重]
func _pick_weighted(rows: Array) -> Array:
	var total := 0.0
	for r in rows:
		total += float(r[2])
	var roll := rng.randf() * total
	for r in rows:
		roll -= float(r[2])
		if roll <= 0.0:
			return r
	return rows[0]


## 从这位顾客的台词池里随机取一句。
func line(kind: String) -> String:
	var pool: Array = persona.get(kind, [""])
	return str(pool[rng.randi_range(0, pool.size() - 1)]).replace("{ask}", str(ask))


## 查看第 i 条线索，返回线索文字。
func reveal(i: int) -> String:
	clues[i].revealed = true
	return "%s：%s" % [clues[i].part, clues[i].text]


## 质疑顾客说的来历，可以反复质疑，每次都消耗耐心。
## 撒谎的人：拿出矛盾的线索就会被揭穿；没证据时，第二次起有机会自己心虚招认。
## 老实人：每次都更生气。返回 {text, mood}，mood 为 caught / confess / unproven / honest。
func challenge() -> Dictionary:
	challenge_count += 1
	if lying and not exposed:
		var lie_seen := false
		for c in clues:
			if c.is_lie and c.revealed:
				lie_seen = true
		var confess := challenge_count >= 2 and rng.randf() < float(tuning.confess_chance)
		if lie_seen or confess:
			exposed = true
			# 被揭穿就说实话：要价降到真实价值，底价再低一截，揭穿骗子一定有赚头
			min_price = _round10(true_value * float(tuning.exposed_floor_ratio))
			ask = maxi(min_price, _round10(true_value * float(tuning.exposed_ask_ratio)))
			return {"text": "“%s”" % line("caught"), "mood": "caught" if lie_seen else "confess"}
		patience -= float(tuning.challenge_unproven_loss)
		return {"text": "“%s”" % line("deny"), "mood": "unproven"}
	patience -= float(tuning.challenge_honest_loss) * challenge_count
	return {"text": "“%s”" % line("offended"), "mood": "honest"}


## 玩家出价。返回 {result, text}，result 为 accept / counter / leave。
func offer(amount: int) -> Dictionary:
	if amount >= min_price:
		return {"result": "accept", "text": "“%s”" % line("accept")}
	rounds_left -= 1
	var gap := float(min_price - amount) / float(min_price)
	patience -= float(tuning.patience_base_loss) + float(tuning.patience_gap_loss) * gap
	if patience <= 0.0 or rounds_left <= 0:
		return {"result": "leave", "text": "“%s”" % line("leave")}
	ask = maxi(_round10(maxf(min_price * float(tuning.counter_floor), (amount + ask) / 2.0)), min_price)
	return {"result": "counter", "text": "“%s”" % line("counter")}


## 卖出这件货能赚多少（付出 paid 之后）。
func profit(paid: int) -> int:
	return true_value - paid


func _round10(v: float) -> int:
	return maxi(10, roundi(v / 10.0) * 10)

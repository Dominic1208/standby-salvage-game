class_name Deal
extends RefCounted
## 一笔交易的全部规则：顾客、货物真实价值、鉴定、质疑来历、砍价。
## 不碰界面，方便以后写单元测试。所有数值来自 data/tuning.json。

var tuning: Dictionary
var item: Dictionary          ## 货物原始数据
var customer: String
var lying: bool
var story: String
var clues: Array = []         ## [{part, text, mult, revealed, is_lie}]
var true_value: int           ## 收购商日终真正会付的钱
var ask: int                  ## 顾客当前要价
var min_price: int            ## 顾客心里的底价（玩家看不到）
var patience: float
var rounds_left: int
var challenged := false


## 用货物表、顾客名单和随机数生成器创建一位新顾客。
func _init(p_tuning: Dictionary, items: Array, customers: Array, rng: RandomNumberGenerator) -> void:
	tuning = p_tuning
	item = items[rng.randi_range(0, items.size() - 1)]
	customer = customers[rng.randi_range(0, customers.size() - 1)]
	lying = item.has("lie") and rng.randf() < float(tuning.lie_chance)
	story = item.lie.story if lying else item.story

	var value := float(item.base)
	for i in item.clues.size():
		var c: Dictionary = item.clues[i].duplicate()
		c["revealed"] = false
		c["is_lie"] = false
		if lying and int(item.lie.clue) == i:
			c["text"] = item.lie.text
			c["mult"] = 1.0
			c["is_lie"] = true
		value *= float(c.mult)
		clues.append(c)
	if lying:
		value *= float(item.lie.mult)
	true_value = roundi(value * rng.randf_range(0.9, 1.1))

	ask = _round10(float(item.base) * rng.randf_range(tuning.greed_min, tuning.greed_max))
	var floor_ratio := rng.randf_range(tuning.min_price_min, tuning.min_price_max)
	if lying:
		floor_ratio *= float(tuning.liar_min_factor)
	min_price = mini(_round10(true_value * floor_ratio), ask)
	patience = float(tuning.patience_start)
	rounds_left = int(tuning.haggle_rounds)


## 查看第 i 条线索，返回线索文字。
func reveal(i: int) -> String:
	clues[i].revealed = true
	return "%s：%s" % [clues[i].part, clues[i].text]


## 质疑顾客说的来历。返回 {text, mood}，mood 为 caught / unproven / honest。
func challenge() -> Dictionary:
	challenged = true
	if lying:
		var lie_seen := false
		for c in clues:
			if c.is_lie and c.revealed:
				lie_seen = true
		if lie_seen:
			min_price = _round10(min_price * float(tuning.challenge_caught_factor))
			ask = maxi(min_price, _round10(ask * 0.8))
			return {"text": "顾客脸色一变：“行吧行吧……便宜点给你，别多问。”", "mood": "caught"}
		patience -= float(tuning.challenge_unproven_loss)
		return {"text": "顾客冷笑：“你有证据吗？”", "mood": "unproven"}
	patience -= float(tuning.challenge_honest_loss)
	return {"text": "顾客很不高兴：“我好心来卖东西，你怀疑我？”", "mood": "honest"}


## 玩家出价。返回 {result, text}，result 为 accept / counter / leave。
func offer(amount: int) -> Dictionary:
	if amount >= min_price:
		return {"result": "accept", "text": "顾客点点头：“成交。”"}
	rounds_left -= 1
	var gap := float(min_price - amount) / float(min_price)
	patience -= float(tuning.patience_base_loss) + float(tuning.patience_gap_loss) * gap
	if patience <= 0.0:
		return {"result": "leave", "text": "顾客气得把东西收回去：“你这是抢钱！”"}
	if rounds_left <= 0:
		return {"result": "leave", "text": "顾客摇摇头：“谈不拢，算了。”"}
	ask = maxi(_round10(maxf(min_price * float(tuning.counter_floor), (amount + ask) / 2.0)), min_price)
	return {"result": "counter", "text": "顾客想了想：“%d，不能再少了。”" % ask}


## 卖出这件货能赚多少（付出 paid 之后）。
func profit(paid: int) -> int:
	return true_value - paid


func _round10(v: float) -> int:
	return maxi(10, roundi(v / 10.0) * 10)

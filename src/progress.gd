class_name Progress
extends RefCounted
## 长期进度：店铺升级、员工造型抽卡、成就。全部永久保留（输了、通关了、重开都还在）。
## 数据在 data/meta.json。花钱的地方都从 main.gd 的现金里扣，所以这里只管规则，不碰界面。

signal achievement_unlocked(a: Dictionary)

var meta: Dictionary
var upgrades := {}        ## 升级 id -> 等级
var skins := {}           ## 拥有的员工造型 look -> true
var stats := {}           ## 成就用的统计 stat -> 数值
var ach := {}             ## 已解锁成就 id -> 解锁时间（unix 秒）


func _init(p_meta: Dictionary) -> void:
	meta = p_meta


## 第一次玩：送 4 个普通造型
func give_starter_skins() -> void:
	if not skins.is_empty():
		return
	for s in meta.gacha.skins.slice(0, 4):
		skins[s.look] = true


# ---------------- 升级 ----------------

func upgrade_def(id: String) -> Dictionary:
	for u in meta.upgrades:
		if u.id == id:
			return u
	return {}


func level(id: String) -> int:
	return int(upgrades.get(id, 0))


## 某个升级当前生效的数值（没买为 0）
func value(id: String) -> float:
	var lv := level(id)
	return float(upgrade_def(id).levels[lv - 1].value) if lv > 0 else 0.0


## 下一级的价钱；已满级返回 -1
func next_cost(id: String) -> int:
	var u := upgrade_def(id)
	var lv := level(id)
	return int(u.levels[lv].cost) if lv < u.levels.size() else -1


func buy_upgrade(id: String) -> void:
	upgrades[id] = level(id) + 1
	bump("upgrades")
	var maxed := 0
	for u in meta.upgrades:
		if level(u.id) >= u.levels.size():
			maxed += 1
	set_stat("maxed_upgrades", maxed)


# ---------------- 抽造型 ----------------

func _roll_skin(rng: RandomNumberGenerator) -> Dictionary:
	var rs: Array = meta.gacha.rarities
	var total := 0.0
	for r in rs:
		total += float(r.weight)
	var roll := rng.randf() * total
	var rar: Dictionary = rs[0]
	for r in rs:
		roll -= float(r.weight)
		if roll <= 0.0:
			rar = r
			break
	var pool: Array = meta.gacha.skins.filter(func(s): return s.rarity == rar.id)
	if pool.is_empty():
		pool = meta.gacha.skins
	return pool[rng.randi_range(0, pool.size() - 1)]


## 抽 n 次（钱由调用方先扣）。返回 [{skin, fresh, refund}]，refund 是重复退回的钱。
func draw(n: int, rng: RandomNumberGenerator) -> Array:
	var out := []
	for i in n:
		var skin := _roll_skin(rng)
		var fresh := not skins.has(skin.look)
		skins[skin.look] = true
		out.append({"skin": skin, "fresh": fresh, "refund": 0 if fresh else int(meta.gacha.dupe_refund)})
		bump("draws")
		if skin.rarity == "ssr":
			bump("ssr")
	set_stat("skins", skins.size())
	return out


func rarity_def(id: String) -> Dictionary:
	for r in meta.gacha.rarities:
		if r.id == id:
			return r
	return meta.gacha.rarities[0]


func skin_def(look: String) -> Dictionary:
	for s in meta.gacha.skins:
		if s.look == look:
			return s
	return {}


# ---------------- 成就 ----------------

func bump(stat: String, n := 1) -> void:
	stats[stat] = int(stats.get(stat, 0)) + n
	check()


func set_max(stat: String, v: int) -> void:
	if v > int(stats.get(stat, 0)):
		stats[stat] = v
		check()


func set_stat(stat: String, v: int) -> void:
	stats[stat] = v
	check()


func check() -> void:
	for a in meta.achievements:
		if ach.has(a.id):
			continue
		if int(stats.get(a.stat, 0)) >= int(a.goal):
			ach[a.id] = int(Time.get_unix_time_from_system())
			achievement_unlocked.emit(a)


## 收藏品相关的统计：不同件数、集齐的系列数、五星件数
func refresh_collection(collection: Dictionary, collectibles: Array) -> void:
	var series := {}
	var legend := 0
	for c in collectibles:
		var s := str(c.get("series", "其他"))
		if not series.has(s):
			series[s] = [0, 0]
		series[s][1] += 1
		if collection.has(c.id):
			series[s][0] += 1
			if int(c.rarity) >= 5:
				legend += 1
	var done := 0
	for s in series.values():
		if s[0] == s[1]:
			done += 1
	set_stat("collection", collection.size())
	set_stat("series_done", done)
	set_stat("legend_items", legend)


func to_dict() -> Dictionary:
	return {"upgrades": upgrades, "skins": skins, "stats": stats, "ach": ach}


func from_dict(d) -> void:
	if typeof(d) != TYPE_DICTIONARY:
		return
	upgrades = d.get("upgrades", {})
	skins = d.get("skins", {})
	stats = d.get("stats", {})
	ach = d.get("ach", {})

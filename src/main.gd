extends Control
## 待机回收站 · 主界面（竖屏）。
## 一笔交易：顾客上门 → 鉴定线索 → 质疑来历（可选）→ 三轮砍价 → 成交或拒绝。
## 回合制，没有实时计时器；外壳发来 pause 时盖上暂停层，什么都不会丢。
## 界面全部用代码搭建：店铺场景、当票式货物卡、收银机式出价区。

# ---- 配色：暗夜杂货铺 + 暖色霓虹 + 旧纸当票 ----
const COL_BG_TOP := Color("2b1e17")
const COL_BG_BOTTOM := Color("0e0b09")
const COL_NEON := Color("ffb347")
const COL_NEON_PINK := Color("ff6b8b")
const COL_TEXT := Color("f6ede2")
const COL_MUTED := Color("a8998a")
const COL_PAPER := Color("efe1c6")
const COL_PAPER_DARK := Color("d9c6a3")
const COL_INK := Color("3a2618")
const COL_INK_SOFT := Color("7a5d44")
const COL_STAMP := Color("c8372d")
const COL_OK := Color("4cd18a")
const COL_BAD := Color("ff5d5d")
const COL_LCD_BG := Color("0d1a13")
const COL_LCD := Color("7dffb2")
const COL_METAL := Color("1c1815")
const CUSTOMER_COLORS := [Color("6c8ebf"), Color("c27c5a"), Color("7fa66a"), Color("a77bc2"),
	Color("c9a04a"), Color("5fa3a0"), Color("b8606f"), Color("8a8f99")]

var tuning: Dictionary
var catalog: Dictionary       ## 货物库 data/catalog.json
var customers: Array          ## 顾客原型 data/customers.json
var personas: Dictionary
var rng := RandomNumberGenerator.new()
var reputation := 0           ## 街坊口碑：公道交易、揭穿骗子会涨，压榨老实人会跌
var order_tag := ""           ## 今天收购商高价收的类别
var run_state := "playing"    ## playing / day_end / lost / won

var cash: int
var day := 1
var time_left: int
var inventory: Array = []     ## 当天收进来的货 [{name, paid, value, leaky}]
var deal: Deal
var offer_amount := 0
var deal_open := false

# 界面节点
var hud_day: Label
var hud_cash: Label
var hud_rep: Label
var order_label: Label
var shop_bg: TextureRect
var portrait: TextureRect
var item_icon: TextureRect
var tag_label: Label
var float_layer: Control
var time_pips: HBoxContainer
var scene_panel: Control
var figure: Control
var figure_color := Color.WHITE
var figure_initial := ""
var name_label: Label
var patience_pips: HBoxContainer
var bubble: PanelContainer
var story_label: Label
var ticket: PanelContainer
var item_label: Label
var ask_stamp: PanelContainer
var ask_label: Label
var clue_box: VBoxContainer
var challenge_btn: Button
var log_label: Label
var offer_label: Label
var round_pips: HBoxContainer
var offer_btn: Button
var take_btn: Button
var refuse_btn: Button
var minus_btn: Button
var plus_btn: Button
var result_layer: Control
var result_card: PanelContainer
var result_title: Label
var result_big: Label
var result_label: Label
var result_btn: Button
var pause_layer: ColorRect
var pause_label: Label

var gifts_data: Dictionary    ## data/gifts.json
var gift_queue: Array = []    ## 还没拆的包裹 ["small" / "big" / "weird"]
var gifts_today := 0
var collection := {}          ## 收藏品 id -> 数量（跨局保留）
var intel := 0                ## 情报：下几次看线索免费、不耗时
var gift_btn: Button
var book_btn: Button
var gift_layer: ColorRect
var gift_art: TextureRect
var gift_title: Label
var gift_body: Label
var gift_action: Button
var gift_opened := false
var book_layer: ColorRect
var book_grid: GridContainer
var book_count: Label
var book_close: Button
var book_series := ""                ## 图鉴正在看的系列；空 = 系列列表
const SAVE_PATH := "user://save.json"
## 每个 AI 工具一种代表色：同一个工具的员工共用颜色，长相不同
const AGENT_COLORS := {"claude": Color("e8875f"), "codex": Color("f4f4f4"), "deepseek": Color("4d6bfe"),
	"grok": Color("1e1e1e"),
	"kimi": Color("f06292"), "glm": Color("26a69a"), "gemini": Color("f2c14e"), "qwen": Color("a98bff"),
	"copilot": Color("4fd1d9"), "cursor": Color("e6e6e6")}
const AGENT_NAMES := {"claude": "Claude", "codex": "Codex", "deepseek": "DeepSeek", "kimi": "Kimi", "grok": "Grok",
	"glm": "智谱", "gemini": "Gemini", "qwen": "Qwen", "copilot": "Copilot", "cursor": "Cursor"}
const SCARF_SHADER := preload("res://canvas_char_apron_tint.gdshader")
## 本身就有大片白色（熊猫、企鹅、宇航服）的形象不染色，只靠工牌和光圈区分
const NO_TINT_LOOKS := ["codex_3", "codex_6", "special_1", "claude_4"]
const STATUS_TEXT := {"working": "干活中", "waiting": "等你拍板！", "resting": "歇着呢"}
var employees: Array = []     ## 外壳发来的员工名单 [{id, agent, name, look, status}]
var home_layer: Control
var room: HomeRoom
var home_info: Label
var home_empty: Label
var dialog_layer: Control
var dialog_portrait: TextureRect
var dialog_name: Label
var dialog_text: Label
var dialog_buttons: HBoxContainer
var _dialog_tween: Tween
var settings_layer: ColorRect

var music_slider: HSlider
var sfx_slider: HSlider
var settings := {"music": 0.6, "sfx": 1.0, "reports": true}
var reports_check: CheckButton
var emergency_used := false    ## 这一局借过应急款了吗
var extra_due := {}            ## 应急款加到哪天还：{"7": 1000}
var result_btn2: Button

var progress: Progress        ## 店铺升级、员工造型、成就（永久保留）
var meta_ui: MetaUI
var last_ratio := 0.0         ## 上一次点的快捷出价成数（“铁公鸡”成就用）

var _web := false
var _poll := 0.0


func _ready() -> void:
	tuning = _load_json("res://data/tuning.json")
	catalog = _load_json("res://data/catalog.json")
	customers = _load_json("res://data/customers.json").archetypes
	personas = _load_json("res://data/personalities.json").types
	gifts_data = _load_json("res://data/gifts.json")
	progress = Progress.new(_load_json("res://data/meta.json"))
	rng.randomize()
	cash = int(tuning.start_cash)
	time_left = int(tuning.time_per_day)
	_build_ui()
	meta_ui = MetaUI.new()
	add_child(meta_ui)
	meta_ui.setup(self, progress)
	_web = OS.has_feature("web")
	if _web:
		JavaScriptBridge.eval("""
			window.__ssq = [];
			window.addEventListener('message', function (e) {
				if (e.origin === location.origin && e.data && e.data.type) window.__ssq.push(e.data);
			});
			if (window.parent !== window) window.parent.postMessage({type: 'game-ready'}, location.origin);
		""", true)
	_bgm("shop")
	if not _load_game():
		_start_day()
	progress.give_starter_skins()
	_show_home.call_deferred()
	_request_employees()


func _process(delta: float) -> void:
	if not _web:
		return
	_poll += delta
	if _poll < 0.15:
		return
	_poll = 0.0
	var raw = JavaScriptBridge.eval("JSON.stringify(window.__ssq ? window.__ssq.splice(0) : [])", true)
	if typeof(raw) != TYPE_STRING:
		return
	var msgs = JSON.parse_string(raw)
	if typeof(msgs) != TYPE_ARRAY:
		return
	for m in msgs:
		_on_shell_message(m)


## 外壳发来的消息：pause / resume / employee。游戏只做表现，不处理任何批准。
func _on_shell_message(m: Dictionary) -> void:
	match str(m.get("type", "")):
		"pause":
			_show_pause(true)
		"resume":
			_show_pause(false)
			# 员工汇报完（或被跳过）回到主页：带回来的包裹当场拆
			if home_layer.visible and not gift_queue.is_empty() and not gift_layer.visible:
				get_tree().create_timer(0.5).timeout.connect(_open_gift)
		"employees":
			_set_employees(m.get("list", []))
		"load-save":
			if _apply_save(m.get("data")):
				_float_text("已从电脑恢复存档", COL_NEON)
				_refresh()
		"gift":
			_receive_gift(str(m.get("tier", "small")), str(m.get("agent", "")))
		"stat":
			progress.bump(str(m.get("name", "")), int(m.get("n", 1)))
			_save_game()
		"employee":
			# 员工的对话框由网页外壳画（带立绘），这里只把游戏调暗、挡住点击
			pause_label.text = ""
			_show_pause(true)


func _show_pause(on: bool) -> void:
	if on == pause_layer.visible:
		return
	pause_layer.visible = on
	if on:
		pause_layer.modulate.a = 0.0
		create_tween().tween_property(pause_layer, "modulate:a", 1.0, 0.2)


# ---------------- 流程 ----------------

func _start_day() -> void:
	_bgm("shop")
	run_state = "playing"
	time_left = _day_length()
	intel += int(progress.value("newsdesk"))
	progress.set_max("best_day_reached", day)
	if Time.get_datetime_dict_from_system().hour < 5:
		progress.set_max("night", 1)
	var tags: Array = tuning.order_tags
	order_tag = tags[rng.randi_range(0, tags.size() - 1)]
	order_label.text = "今日订单：收购商高价收【%s】类，%.1f 倍" % [order_tag, float(tuning.order_bonus)]
	_next_customer()
	_float_text("第 %d 天开张" % day, COL_NEON)


## 每天的营业时间：基础 + 霓虹招牌
func _day_length() -> int:
	return int(tuning.time_per_day) + int(progress.value("sign"))


func _next_customer() -> void:
	if time_left < int(tuning.time_per_customer) + 1:
		_end_day()
		return
	time_left -= int(tuning.time_per_customer)
	deal = Deal.new(tuning, catalog, customers, personas, rng, reputation)
	deal.patience *= 1.0 + progress.value("charm")
	if progress.level("appraiser") > 0:  # 老鉴定师：每位顾客免费看一处
		deal.reveal(rng.randi_range(0, deal.clues.size() - 1))
	deal_open = true
	var cname: String = deal.customer.name
	offer_amount = clampi(deal.ask, 10, maxi(cash, 10))  # 出价屏先显示顾客的要价，点 5/7/9 成再变
	figure_color = CUSTOMER_COLORS[absi(hash(deal.customer.art)) % CUSTOMER_COLORS.size()]
	figure_initial = cname.substr(0, 1)
	portrait.texture = _art(deal.customer.get("art", ""))
	figure.queue_redraw()
	item_icon.texture = _art(deal.item.get("art", ""))
	item_icon.visible = item_icon.texture != null
	name_label.text = cname
	story_label.text = "“%s”" % deal.story
	item_label.text = deal.item.name
	var hot := str(deal.item.get("tag", "")) == order_tag
	tag_label.text = (("【%s】今日订单！" % deal.item.tag) if hot else ("【%s】" % deal.item.get("tag", ""))) 		+ "　市场参考价 ¥%d" % int(deal.item.base)
	tag_label.add_theme_color_override("font_color", COL_STAMP if hot else COL_INK_SOFT)
	_log("“%s”" % deal.line("greet"), COL_TEXT)
	_build_clues()
	_refresh()
	_animate_arrival()
	_sfx("door")


func _animate_arrival() -> void:
	figure.modulate.a = 0.0
	figure.position = Vector2(146, 40)
	bubble.modulate.a = 0.0
	ticket.modulate.a = 0.0
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(figure, "position:x", 16.0, 0.35)
	tw.parallel().tween_property(figure, "modulate:a", 1.0, 0.3)
	tw.tween_property(bubble, "modulate:a", 1.0, 0.2)
	tw.tween_property(ticket, "modulate:a", 1.0, 0.2)


func _build_clues() -> void:
	for c in clue_box.get_children():
		c.queue_free()
	for i in deal.clues.size():
		var b := _clue_button("◎  检查%s" % deal.clues[i].part, "耗时 %d" % int(tuning.time_per_clue))
		b.pressed.connect(_on_clue.bind(i, b))
		clue_box.add_child(b)
		if deal.clues[i].revealed:
			_mark_clue(b, "%s：%s（老鉴定师看的）" % [deal.clues[i].part, deal.clues[i].text])


func _mark_clue(b: Button, text: String) -> void:
	b.text = "✓  " + text
	b.disabled = true
	b.add_theme_stylebox_override("disabled", _revealed_box())
	b.add_theme_color_override("font_disabled_color", COL_INK)
	b.get_meta("cost").visible = false


func _on_clue(i: int, b: Button) -> void:
	if not deal_open or deal.clues[i].revealed:
		return
	if intel <= 0 and time_left < int(tuning.time_per_clue):
		_log("今天没时间细看了。", COL_BAD)
		return
	if intel > 0:
		intel -= 1
		_float_text("（用掉一条情报，不耗时）", COL_NEON)
	elif rng.randf() < progress.value("lens"):
		_float_text("（放大镜：一眼看穿，不耗时）", COL_NEON)
	else:
		time_left -= int(tuning.time_per_clue)
	var text := deal.reveal(i)
	_sfx("clue")
	_mark_clue(b, text)
	_pulse(b)
	_refresh()


func _on_challenge() -> void:
	if not deal_open or deal.exposed:
		return
	var r := deal.challenge()
	_log(r.text, COL_OK if r.mood in ["caught", "confess"] else COL_BAD)
	if r.mood in ["caught", "confess"]:
		_pulse(ask_stamp)
		tag_label.text = "【%s】揭穿了：它其实只值 ¥%d 左右" % [deal.item.get("tag", ""), deal.ask]
		tag_label.add_theme_color_override("font_color", COL_OK)
		_change_rep(1, "揭穿了骗子")
		progress.bump("liars")
		_sfx("caught")
	else:
		if r.mood == "honest":
			progress.bump("wrong_accuse")
		_shake(figure)
		_sfx("angry")
	if deal.patience <= 0:
		_close_deal(false, "顾客扭头就走了。")
		return
	offer_amount = mini(offer_amount, deal.ask)
	_refresh()


func _on_offer() -> void:
	if not deal_open:
		return
	if offer_amount > cash:
		_log("钱不够了。", COL_BAD)
		return
	var r := deal.offer(offer_amount)
	match r.result:
		"accept":
			_log(r.text, COL_OK)
			_buy(offer_amount)
		"leave":
			_log(r.text, COL_BAD)
			_close_deal(false, r.text)
		_:
			_log(r.text, COL_TEXT)
			_sfx("counter")
			_shake(figure)
			_pulse(ask_stamp)
			_refresh()


func _on_quick_offer(ratio: float) -> void:
	if not deal_open:
		return
	offer_amount = clampi(roundi(deal.ask * ratio / 10.0) * 10, 10, mini(maxi(cash, 10), deal.ask))
	last_ratio = ratio
	_refresh()
	_pulse(offer_label)


func _on_take() -> void:
	if deal_open and deal.ask <= cash:
		_log("“%s”" % deal.line("accept"), COL_OK)
		_buy(deal.ask)


func _on_refuse() -> void:
	if deal_open:
		_close_deal(false, "你摆摆手，%s 带着%s走了。" % [deal.customer.name, deal.item.name])


func _buy(price: int) -> void:
	cash -= price
	_sfx("coin")
	inventory.append({"name": deal.item.name, "paid": price, "value": deal.true_value,
		"leaky": deal.item.get("leaky", false), "tag": deal.item.get("tag", "")})
	# 口碑：对老实人给公道价会涨，压榨会跌
	if not deal.lying:
		var ratio := float(price) / maxf(1.0, deal.true_value)
		if ratio >= float(tuning.rep_fair_ratio):
			_change_rep(1, "给了公道价")
		elif ratio < float(tuning.rep_lowball_ratio):
			_change_rep(-1, "压价太狠")
	var p := deal.profit(price)
	progress.bump("deals")
	progress.set_max("best_profit", p)
	progress.set_max("worst_loss", -p)
	if str(deal.item.get("tag", "")) == order_tag:
		progress.bump("order_items")
	if last_ratio > 0.0 and last_ratio <= 0.31 and price == offer_amount:
		progress.bump("lowball")
	var lines := ["%s　付出 ¥%d" % [deal.item.name, price], "收购商估价 ¥%d" % deal.true_value]
	if str(deal.item.get("tag", "")) == order_tag:
		lines.append("符合今日订单，打烊时按 %.1f 倍收" % float(tuning.order_bonus))
	if deal.lying:
		lines.append("顾客说了谎：%s" % _lie_text())
	if deal.item.get("leaky", false):
		lines.append("注意：这是会漏液的问题货，可能弄坏仓库里别的货")
	_show_result("成交", ("+¥%d" % p) if p >= 0 else ("-¥%d" % -p), COL_OK if p >= 0 else COL_BAD,
		"\n".join(lines))


func _change_rep(delta: int, why: String) -> void:
	reputation += delta
	progress.set_max("best_rep", reputation)
	_float_text("（街坊口碑 %s%d · %s）" % ["+" if delta > 0 else "", delta, why], COL_OK if delta > 0 else COL_BAD)
	_refresh()


func _lie_text() -> String:
	for c in deal.clues:
		if c.is_lie:
			return "%s%s" % [c.part, c.text]
	return ""


func _close_deal(_bought: bool, text: String) -> void:
	_sfx("leave")
	_show_result("没谈成", "¥0", COL_MUTED, "%s\n\n它其实值 ¥%d" % [text, deal.true_value])


func _show_result(title: String, big: String, big_color: Color, body: String) -> void:
	deal_open = false
	result_title.text = title
	result_big.text = big
	result_big.add_theme_color_override("font_color", big_color)
	result_label.text = body
	result_btn.text = "下一位顾客" if time_left >= int(tuning.time_per_customer) + 1 else "打烊结算"
	_open_result()
	_refresh()


func _open_result() -> void:
	_save_game()
	result_layer.visible = true
	result_layer.modulate.a = 0.0
	result_card.scale = Vector2(0.85, 0.85)
	result_card.pivot_offset = result_card.size / 2
	var tw := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(result_layer, "modulate:a", 1.0, 0.15)
	tw.parallel().tween_property(result_card, "scale", Vector2.ONE, 0.3)


func _on_result_next() -> void:
	result_layer.visible = false
	result_btn2.visible = false
	if run_state == "bankrupt":
		_take_emergency_loan()
		return
	if run_state == "playing" and _is_broke():
		_show_bankrupt()
		return
	match run_state:
		"day_end":
			_start_day()
		"lost", "won":
			_restart()
		_:
			_next_customer()


## 破产：钱不够收任何东西，仓库也是空的
func _is_broke() -> bool:
	return cash < 50 and inventory.is_empty()


func _show_bankrupt() -> void:
	deal_open = false
	progress.bump("bankrupts")
	result_title.text = "破产了"
	result_big.text = "¥%d" % cash
	result_big.add_theme_color_override("font_color", COL_BAD)
	if not emergency_used:
		var due := _next_due(day)
		run_state = "bankrupt"
		result_label.text = "钱花光了，仓库也空了。\n\n银行愿意借你一笔应急款 ¥%d，\n第 %d 天还款时要多还 ¥%d。\n（每局只能借一次）" % [
			int(tuning.emergency_loan), due.x if due.x > 0 else int(tuning.run_days), int(tuning.emergency_repay)]
		result_btn.text = "借应急款"
		result_btn2.visible = true
	else:
		run_state = "lost"
		result_label.text = "钱花光了，应急款也借过了……\n店只能先关门了。\n\n收藏品会保留，下一局再来！"
		result_btn.text = "从头再来"
	_sfx("lose")
	_open_result()


func _take_emergency_loan() -> void:
	emergency_used = true
	cash += int(tuning.emergency_loan)
	var due := _next_due(day)
	var key := str(due.x if due.x > 0 else int(tuning.run_days))
	extra_due[key] = int(extra_due.get(key, 0)) + int(tuning.emergency_repay)
	run_state = "playing"
	_float_text("借到应急款 ¥%d" % int(tuning.emergency_loan), COL_NEON)
	_sfx("coin")
	_next_customer()


func _restart() -> void:
	emergency_used = false
	extra_due = {}
	day = 1
	cash = int(tuning.start_cash)
	reputation = 0
	inventory.clear()
	_start_day()


func _end_day() -> void:
	var lines: Array = []
	# 漏液的问题货会弄坏仓库里另一件货
	var leaky := inventory.filter(func(it): return it.leaky)
	if not leaky.is_empty() and inventory.size() > 1 and progress.level("safe") == 0:
		var victims := inventory.filter(func(it): return not it.leaky)
		if not victims.is_empty():
			var v: Dictionary = victims[rng.randi_range(0, victims.size() - 1)]
			var loss := roundi(int(v.value) * float(tuning.leak_damage))
			v.value = int(v.value) - loss
			lines.append("漏液弄坏了%s，少卖 ¥%d" % [v.name, loss])
	var total := 0
	var paid := 0
	var bonus := 0
	var buyer := 1.0 + progress.value("buyer")
	for it in inventory:
		var value := roundi(int(it.value) * buyer)
		if str(it.tag) == order_tag:
			var extra := roundi(value * (float(tuning.order_bonus) - 1.0))
			bonus += extra
			value += extra
		total += value
		paid += int(it.paid)
	cash += total
	var net := total - paid
	progress.set_max("best_day", net)
	lines.push_front("收了 %d 件货，花了 ¥%d" % [inventory.size(), paid])
	lines.insert(1, "收购商一共付了 ¥%d" % total)
	if bonus > 0:
		lines.insert(2, "其中订单加价 ¥%d" % bonus)
	inventory.clear()

	result_title.text = "第 %d 天 打烊" % day
	result_big.text = ("+¥%d" % net) if net >= 0 else ("-¥%d" % -net)
	result_big.add_theme_color_override("font_color", COL_OK if net >= 0 else COL_BAD)
	run_state = "day_end"
	var due := int(tuning.loan_due.get(str(day), 0)) + int(extra_due.get(str(day), 0))
	if due > 0:
		if cash >= due:
			cash -= due
			lines.append("\n还贷 ¥%d ✓ 收债人点点头走了" % due)
			progress.bump("loans_paid")
		else:
			lines.append("\n今天要还贷 ¥%d，你只有 ¥%d……\n收债人把店门锁上了。" % [due, cash])
			run_state = "lost"
	lines.append("现金 ¥%d　口碑 %d" % [cash, reputation])
	if run_state == "day_end" and day >= int(tuning.run_days):
		run_state = "won"
		progress.bump("wins")
		if emergency_used:
			progress.bump("comebacks")
		lines.append("\n贷款全部还清，这家店归你了。\n店铺升级、员工造型、收藏品都会保留。")
	elif run_state == "day_end":
		var next_due := _next_due(day + 1)
		if next_due.x > 0:
			lines.append("下次还贷：第 %d 天 ¥%d" % [next_due.x, next_due.y])
	result_label.text = "\n".join(lines)
	match run_state:
		"lost":
			result_title.text = "店被收走了"
			result_btn.text = "从头再来"
		"won":
			result_title.text = "七天撑过来了！"
			result_btn.text = "再开一局"
		_:
			result_btn.text = "开始第 %d 天" % (day + 1)
	if run_state == "day_end":
		day += 1
	gifts_today = 0
	deal_open = false
	_sfx({"lost": "lose", "won": "win"}.get(run_state, "day_end"))
	_bgm("closing" if run_state == "day_end" else "")
	_open_result()
	_save_game()
	_refresh()


func _next_due(from_day: int) -> Vector2i:
	for d in range(from_day, int(tuning.run_days) + 1):
		var amount := int(tuning.loan_due.get(str(d), 0)) + int(extra_due.get(str(d), 0))
		if amount > 0:
			return Vector2i(d, amount)
	return Vector2i.ZERO


func _change_offer(sign_dir: int) -> void:
	var step := maxi(10, roundi(deal.ask * float(tuning.offer_step_ratio) / 10.0) * 10)
	offer_amount = clampi(offer_amount + sign_dir * step, 10, mini(maxi(cash, 10), deal.ask))
	last_ratio = 0.0
	_refresh()
	_pulse(offer_label)


func _float_text(text: String, color: Color) -> void:
	var l := _label(text, 26, color)
	l.add_theme_constant_override("outline_size", 8)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.set_anchors_preset(Control.PRESET_TOP_WIDE)
	l.offset_top = 300
	float_layer.add_child(l)
	var tw := create_tween()
	tw.tween_property(l, "offset_top", 230.0, 1.4).set_trans(Tween.TRANS_SINE)
	tw.parallel().tween_property(l, "modulate:a", 0.0, 1.4).set_delay(0.6)
	tw.tween_callback(l.queue_free)


# ---------------- 主页：员工推门进来 ----------------

## 向外壳要员工名单；外壳可能比游戏先收到名单，所以没拿到就隔 2 秒再要，最多 10 次
func _request_employees(tries := 10) -> void:
	if not _web or tries <= 0 or not employees.is_empty():
		return
	_post_shell("need-employees", {})
	get_tree().create_timer(2.0).timeout.connect(_request_employees.bind(tries - 1))


func _show_home() -> void:
	home_info.text = "第 %d 天　¥%d　口碑 %d" % [day, cash, reputation]
	home_layer.visible = true
	home_layer.modulate.a = 0.0
	create_tween().tween_property(home_layer, "modulate:a", 1.0, 0.25)
	_sfx("tap")
	if not gift_queue.is_empty():
		_open_gift.call_deferred()


func _set_employees(list: Array) -> void:
	employees = list
	progress.set_max("staff", list.size())
	var visible_list := list.filter(func(e): return str(e.get("status", "")) == "waiting" \
		or (bool(settings.get("reports", true)) and bool(e.get("reported", false))))
	home_empty.visible = visible_list.is_empty()
	home_empty.text = ("员工们都出门探险了。\n有事要你拍板、或者带着成果回来时，\n他们会推门进来找你。"
		if not list.is_empty() else "还没有员工报到。\n在电脑设置页把你的 AI 连进来，\n他们就会推门进来。")
	room.set_employees(visible_list, true)


# ---------------- 主页：大本营 ----------------

func _build_home_layer() -> void:
	home_layer = Control.new()
	home_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	room = HomeRoom.new()
	room.art_loader = _art
	room.colors = AGENT_COLORS
	room.tint_shader = SCARF_SHADER
	room.no_tint = NO_TINT_LOOKS
	room.set_anchors_preset(Control.PRESET_FULL_RECT)
	room.open_shop.connect(_hide_home)
	room.staff_tapped.connect(_open_dialog)
	home_layer.add_child(room)

	# 顶部：招牌 + 进度，右上角两个小按钮
	var top := VBoxContainer.new()
	top.set_anchors_preset(Control.PRESET_TOP_WIDE)
	top.offset_top = 18
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var title := _label("待机回收站", 52, COL_NEON_PINK)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_constant_override("outline_size", 16)
	title.add_theme_color_override("font_outline_color", Color(0.1, 0.03, 0.05, 0.85))
	top.add_child(title)
	home_info = _label("", 22, COL_TEXT)
	home_info.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	home_info.add_theme_constant_override("outline_size", 8)
	home_info.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.75))
	top.add_child(home_info)
	home_layer.add_child(top)

	var corner := VBoxContainer.new()
	corner.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	corner.offset_left = -150
	corner.offset_right = -16
	corner.offset_top = 120
	corner.add_theme_constant_override("separation", 10)
	var book := _button("收藏室", Color(0.08, 0.06, 0.05, 0.75), COL_NEON, COL_NEON)
	book.custom_minimum_size = Vector2(134, 54)
	book.add_theme_font_size_override("font_size", 22)
	book.pressed.connect(_open_book)
	var setting := _button("设置", Color(0.08, 0.06, 0.05, 0.75), COL_TEXT, Color("6a5a4c"))
	setting.custom_minimum_size = Vector2(134, 54)
	setting.add_theme_font_size_override("font_size", 22)
	setting.pressed.connect(func() -> void:
		settings_layer.visible = true
		_sfx("tap"))
	corner.add_child(book)
	for entry in [["升级", func() -> void: meta_ui.open_upgrades()], ["抽造型", func() -> void: meta_ui.open_gacha()],
			["成就", func() -> void: meta_ui.open_achievements()]]:
		var mb := _button(entry[0], Color(0.08, 0.06, 0.05, 0.75), COL_NEON, COL_NEON)
		mb.custom_minimum_size = Vector2(134, 54)
		mb.add_theme_font_size_override("font_size", 22)
		mb.pressed.connect(entry[1])
		corner.add_child(mb)
	corner.add_child(setting)
	home_layer.add_child(corner)

	home_empty = _label("还没有员工报到。\n在电脑设置页把你的 AI 连进来，\n他们就会推门进来。", 24, COL_TEXT, true)
	home_empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	home_empty.add_theme_constant_override("outline_size", 8)
	home_empty.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	home_empty.set_anchors_preset(Control.PRESET_CENTER)
	home_empty.offset_left = -300
	home_empty.offset_right = 300
	home_empty.offset_top = -60
	home_empty.mouse_filter = Control.MOUSE_FILTER_IGNORE
	home_empty.visible = false  # 收到名单、确认是空的才显示
	home_layer.add_child(home_empty)
	add_child(home_layer)


# ---------------- 对话框：立绘 + 台词（文字冒险风） ----------------

const DIALOG_LINES := {
	"claude": {"working": ["在忙「{p}」。很快。", "别担心，「{p}」交给我。"],
		"resting": ["「{p}」那边做完了。有新任务再叫我。", "……我在休息。"],
		"waiting": ["「{p}」有一步需要你拍板。", "老板，这一步我不能自己决定。"]},
	"codex": {"working": ["嘿嘿，「{p}」正在搞，别催别催~", "我在「{p}」里翻来翻去找东西！"],
		"resting": ["偷偷吃个小鱼干……老板别告诉别人。", "活干完啦，可以摸会儿鱼吗？"],
		"waiting": ["老板老板！「{p}」有个东西要你点头！", "这个我不敢乱动，你来看看嘛。"]},
	"deepseek": {"working": ["「{p}」我在认真做，你先忙你的。", "慢慢来，会做好的。"],
		"resting": ["老板辛苦啦，我泡了茶，要不要来一杯？", "「{p}」做完了，你要不要看看？"],
		"waiting": ["「{p}」有一步想先问问你的意见。", "不好意思打扰一下，这一步需要你确认。"]},
	"_": {"working": ["正在忙「{p}」。"], "resting": ["「{p}」告一段落，我歇会儿。"],
		"waiting": ["老板，「{p}」有件事要你拍板。"]},
}


func _open_dialog(e: Dictionary) -> void:
	_sfx("tap")
	# 带着汇报回来的员工：点他就直接听汇报（汇报内容在外壳里）
	if bool(e.get("reported", false)) and str(e.get("status", "")) != "waiting":
		_post_shell("open-report", {"employeeId": str(e.id)})
		return
	var look = e.get("look", "staff_1")
	dialog_portrait.texture = _art(str(look))
	var color: Color = AGENT_COLORS.get(e.agent, COL_NEON)
	if not NO_TINT_LOOKS.has(str(look)):
		var mat := ShaderMaterial.new()
		mat.shader = SCARF_SHADER
		mat.set_shader_parameter("tint_color", color)
		dialog_portrait.material = mat
	else:
		dialog_portrait.material = null
	dialog_name.text = "%s · %s" % [str(e.get("name", "员工")), AGENT_NAMES.get(e.agent, str(e.get("label", e.agent)))]
	var plate: StyleBoxFlat = dialog_name.get_parent().get_theme_stylebox("panel")
	plate.bg_color = color
	dialog_name.add_theme_color_override("font_color", Color.WHITE if color.get_luminance() < 0.45 else Color("1a1208"))
	var status := str(e.get("status", "working"))
	var lines: Dictionary = DIALOG_LINES.get(e.agent, DIALOG_LINES["_"])
	var pool: Array = lines.get(status, DIALOG_LINES["_"][status])
	dialog_text.text = str(pool[rng.randi_range(0, pool.size() - 1)]).replace("{p}", str(e.get("project", "")))
	for c in dialog_buttons.get_children():
		c.queue_free()
	if status == "waiting":
		_dialog_button("去看看", COL_NEON, func() -> void:
			_close_dialog()
			_post_shell("open-pending", {"employeeId": str(e.id)}))
	_dialog_button("改名", Color(0.95, 0.9, 0.82), func() -> void:
		_close_dialog()
		progress.bump("renames")
		_post_shell("rename-employee", {"id": str(e.id), "name": str(e.get("name", ""))}))
	_dialog_button("换造型", Color(0.95, 0.9, 0.82), func() -> void:
		_close_dialog()
		meta_ui.open_skin_picker(e, func(look: String) -> void:
			_sfx("gift")
			_post_shell("set-employee-look", {"id": str(e.id), "look": look})))
	dialog_layer.visible = true
	# 立绘滑入 + 文字逐字出现
	dialog_portrait.modulate.a = 0.0
	dialog_portrait.position.x = -60
	dialog_text.visible_ratio = 0.0
	if _dialog_tween:
		_dialog_tween.kill()
	_dialog_tween = create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_dialog_tween.tween_property(dialog_portrait, "modulate:a", 1.0, 0.25)
	_dialog_tween.parallel().tween_property(dialog_portrait, "position:x", 0.0, 0.3)
	_dialog_tween.tween_property(dialog_text, "visible_ratio", 1.0, 0.03 * dialog_text.text.length())


func _dialog_button(text: String, color: Color, action: Callable) -> void:
	var b := _button(text, color, Color("1a1208"))
	b.custom_minimum_size = Vector2(0, 60)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.add_theme_font_size_override("font_size", 22)
	b.pressed.connect(action)
	dialog_buttons.add_child(b)


func _close_dialog() -> void:
	dialog_layer.visible = false


func _build_dialog_layer() -> void:
	dialog_layer = Control.new()
	dialog_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	dialog_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.35)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.gui_input.connect(func(ev: InputEvent) -> void:
		if ev is InputEventMouseButton and ev.pressed:
			_close_dialog())
	dialog_layer.add_child(shade)
	# 大立绘：站在对话框左上方
	var stage := Control.new()
	stage.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	stage.offset_top = -900
	stage.offset_bottom = -250
	stage.offset_left = 0
	stage.offset_right = 470
	stage.mouse_filter = Control.MOUSE_FILTER_IGNORE
	dialog_portrait = TextureRect.new()
	dialog_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	dialog_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	dialog_portrait.set_anchors_preset(Control.PRESET_FULL_RECT)
	dialog_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(dialog_portrait)
	dialog_layer.add_child(stage)
	# 对话框
	var box := PanelContainer.new()
	box.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	box.offset_left = 16
	box.offset_right = -16
	box.offset_top = -300
	box.offset_bottom = -20
	var bsb := _box(Color(0.1, 0.07, 0.05, 0.94), 20)
	bsb.border_color = Color("6a5040")
	bsb.set_border_width_all(3)
	bsb.content_margin_left = 26
	bsb.content_margin_right = 26
	bsb.content_margin_top = 44
	bsb.content_margin_bottom = 20
	box.add_theme_stylebox_override("panel", bsb)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 16)
	dialog_text = _label("", 30, COL_TEXT, true)
	dialog_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(dialog_text)
	dialog_buttons = HBoxContainer.new()
	dialog_buttons.add_theme_constant_override("separation", 12)
	col.add_child(dialog_buttons)
	box.add_child(col)
	dialog_layer.add_child(box)
	# 名字牌：压在对话框左上角，用 AI 代表色
	var plate := PanelContainer.new()
	var psb := _box(COL_NEON, 12)
	psb.content_margin_top = 6
	psb.content_margin_bottom = 6
	plate.add_theme_stylebox_override("panel", psb)
	plate.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	plate.offset_left = 40
	plate.offset_top = -322
	plate.offset_bottom = -276
	dialog_name = _label("", 24, Color("1a1208"))
	plate.add_child(dialog_name)
	dialog_layer.add_child(plate)
	dialog_layer.visible = false
	add_child(dialog_layer)


func _hide_home() -> void:
	home_layer.visible = false
	_sfx("door")


func _post_shell(type: String, fields: Dictionary) -> void:
	if _web:
		var msg := fields.duplicate()
		msg["type"] = type
		JavaScriptBridge.eval("window.parent.postMessage(%s,location.origin)" % JSON.stringify(msg), true)


func _build_settings_layer() -> void:
	settings_layer = ColorRect.new()
	settings_layer.color = Color(0.03, 0.02, 0.02, 0.88)
	settings_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	settings_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(600, 0)
	var sb := _box(COL_PAPER, 22)
	sb.content_margin_left = 30
	sb.content_margin_right = 30
	sb.content_margin_top = 26
	sb.content_margin_bottom = 26
	card.add_theme_stylebox_override("panel", sb)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 16)
	var title := _label("设置", 34, COL_INK)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(title)
	col.add_child(_label("背景音乐", 24, COL_INK))
	music_slider = _slider(settings.music)
	col.add_child(music_slider)
	col.add_child(_label("音效", 24, COL_INK))
	sfx_slider = _slider(settings.sfx)
	col.add_child(sfx_slider)
	reports_check = CheckButton.new()
	reports_check.text = "员工完成任务时，进来汇报完整内容"
	reports_check.add_theme_font_size_override("font_size", 22)
	reports_check.add_theme_color_override("font_color", COL_INK)
	reports_check.add_theme_color_override("font_pressed_color", COL_INK)
	reports_check.add_theme_color_override("font_hover_color", COL_INK)
	reports_check.button_pressed = bool(settings.get("reports", true))
	reports_check.toggled.connect(func(on: bool) -> void:
		settings.reports = on
		_apply_volume()
		_set_employees(employees))
	col.add_child(reports_check)
	col.add_child(_label("关掉后，员工只在需要你批准时进来；完成任务时把包裹放下就走。", 18, COL_INK_SOFT, true))
	var tip := _label("点主页上的员工可以给他改名。\n员工按“AI 工具 + 项目”区分：同一个 AI 的员工领巾和工牌颜色相同。", 20, COL_INK_SOFT, true)
	col.add_child(tip)
	var close := _button("好", COL_NEON, Color("1a1208"))
	close.pressed.connect(func() -> void:
		settings_layer.visible = false
		_save_game())
	col.add_child(close)
	card.add_child(col)
	center.add_child(card)
	settings_layer.add_child(center)
	settings_layer.visible = false
	add_child(settings_layer)


func _slider(value: float) -> HSlider:
	var sl := HSlider.new()
	sl.min_value = 0.0
	sl.max_value = 1.0
	sl.step = 0.05
	sl.value = value
	sl.custom_minimum_size = Vector2(0, 56)
	var grabber_bg := _box(COL_PAPER_DARK, 8)
	grabber_bg.content_margin_top = 8
	grabber_bg.content_margin_bottom = 8
	sl.add_theme_stylebox_override("slider", grabber_bg)
	sl.add_theme_stylebox_override("grabber_area", _box(COL_NEON, 8))
	sl.add_theme_stylebox_override("grabber_area_highlight", _box(COL_NEON, 8))
	sl.value_changed.connect(func(_v: float) -> void:
		settings.music = music_slider.value if music_slider else settings.music
		settings.sfx = sfx_slider.value if sfx_slider else settings.sfx
		_apply_volume())
	return sl


func _apply_volume() -> void:
	if music_slider:
		music_slider.set_value_no_signal(float(settings.music))
		sfx_slider.set_value_no_signal(float(settings.sfx))
		reports_check.set_pressed_no_signal(bool(settings.get("reports", true)))
	if _web:
		JavaScriptBridge.eval("window.parent.postMessage({type:'prefs',reports:%s},location.origin)"
			% ("true" if settings.get("reports", true) else "false"), true)
	if _web:
		JavaScriptBridge.eval("window.parent.postMessage({type:'volume',music:%f,sfx:%f},location.origin)"
			% [float(settings.music), float(settings.sfx)], true)


# ---------------- 员工包裹 ----------------

## 外壳通知：员工带回一个包裹。批准和拒绝给的一样，避免诱导无脑批准。
func _receive_gift(tier: String, _agent: String) -> void:
	if gifts_today >= int(gifts_data.daily_cap):
		_float_text("（今天的包裹已经够多了，员工把它放进了仓库）", COL_MUTED)
		return
	gifts_today += 1
	if tier == "small" and rng.randf() < progress.value("map"):
		tier = "big"
	if tier == "small" and rng.randf() < float(gifts_data.weird_chance):
		tier = "weird"
	gift_queue.append(tier)
	_float_text("员工带回了%s！" % gifts_data.tiers[tier].title, COL_NEON)
	_sfx("notify")
	_refresh()
	_pulse(gift_btn)
	_save_game()
	if home_layer.visible and not gift_layer.visible:
		get_tree().create_timer(0.6).timeout.connect(_open_gift)


func _open_gift() -> void:
	if gift_queue.is_empty():
		return
	var tier: String = gift_queue[0]
	gift_opened = false
	gift_art.texture = _art(gifts_data.tiers[tier].art)
	gift_title.text = gifts_data.tiers[tier].title
	gift_body.text = "点一下拆开看看"
	gift_action.text = "拆开"
	gift_layer.visible = true
	gift_art.pivot_offset = gift_art.size / 2
	var tw := create_tween().set_loops(3)
	tw.tween_property(gift_art, "rotation_degrees", 6.0, 0.08)
	tw.tween_property(gift_art, "rotation_degrees", -6.0, 0.08)
	tw.tween_property(gift_art, "rotation_degrees", 0.0, 0.08)


func _on_gift_action() -> void:
	if gift_opened:
		gift_layer.visible = false
		_refresh()
		return
	if gift_queue.is_empty():  # 包裹窗口开着时存档被替换（例如从电脑恢复存档）
		gift_layer.visible = false
		return
	var tier: String = gift_queue.pop_front()
	var bonus := float(gifts_data.tiers[tier].bonus)
	var o: Dictionary = _pick_weighted_outcome(tier)
	var good := true
	var text := ""
	match str(o.kind):
		"cash":
			var amount := roundi(rng.randi_range(int(o.min), int(o.max)) * (bonus if int(o.min) > 0 else 1.0))
			cash += amount
			good = amount >= 0
			text = "%s\n\n%s ¥%d" % [_pick_text(o), "+" if amount >= 0 else "-", absi(amount)]
		"collectible":
			var c := _roll_collectible(tier)
			var fresh := not collection.has(c.id)
			collection[c.id] = int(collection.get(c.id, 0)) + 1
			gift_art.texture = _art(str(c.get("art", "col_" + str(c.id))))
			text = "%s收藏品：%s %s\n\n%s" % ["新" if fresh else "重复的", c.name, "★".repeat(int(c.rarity)), c.desc]
			if not fresh:
				var refund := 5 * int(c.rarity)
				cash += refund
				text += "\n\n（重复的卖给了收藏贩子 +¥%d）" % refund
		"intel":
			intel += int(o.count)
			text = "%s\n\n情报 +%d：看线索免费、不耗时" % [_pick_text(o), int(o.count)]
		"rep":
			reputation += int(o.amount)
			text = "%s\n\n街坊口碑 +%d" % [_pick_text(o), int(o.amount)]
		_:
			good = false
			text = _pick_text(o)
	progress.bump("gifts")
	progress.refresh_collection(collection, gifts_data.collectibles)
	gift_body.text = text
	gift_title.text = "拆开了！" if good else "呃……"
	gift_action.text = "收下"
	gift_opened = true
	_sfx("gift" if good else "bad_gift")
	gift_art.scale = Vector2(0.6, 0.6)
	create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT) \
		.tween_property(gift_art, "scale", Vector2.ONE, 0.35)
	_refresh()
	_save_game()


func _pick_weighted_outcome(tier: String) -> Dictionary:
	var rows: Array = gifts_data.outcomes
	var total := 0.0
	for r in rows:
		total += float(r.weight) * (0.5 if tier == "big" and int(r.get("min", 0)) < 0 else 1.0)
	var roll := rng.randf() * total
	for r in rows:
		roll -= float(r.weight) * (0.5 if tier == "big" and int(r.get("min", 0)) < 0 else 1.0)
		if roll <= 0.0:
			return r
	return rows[0]


## 稀有度越高越难出；大箱子更容易出稀有的。
func _roll_collectible(tier: String) -> Dictionary:
	var pool: Array = gifts_data.collectibles
	var weights: Array = []
	var total := 0.0
	for c in pool:
		var w := 1.0 / pow(float(c.rarity), 2.0 if tier != "big" else 1.2)
		weights.append(w)
		total += w
	var roll := rng.randf() * total
	for i in pool.size():
		roll -= weights[i]
		if roll <= 0.0:
			return pool[i]
	return pool[0]


func _pick_text(o: Dictionary) -> String:
	var arr: Array = o.get("text", [""])
	return str(arr[rng.randi_range(0, arr.size() - 1)])


# ---------------- 图鉴 ----------------

func _open_book() -> void:
	_show_book_series()
	book_layer.visible = true
	_sfx("tap")


## 收藏品按系列分组（保持 gifts.json 里的顺序）
func _book_groups() -> Array:
	var order: Array = []
	var groups := {}
	for c in gifts_data.collectibles:
		var s := str(c.get("series", "其他"))
		if not groups.has(s):
			groups[s] = []
			order.append(s)
		groups[s].append(c)
	return order.map(func(s): return {"name": s, "items": groups[s]})


## 第一层：系列列表，每个系列显示集了几件。一千多件一次全排出来手机会卡，所以分两层
func _show_book_series() -> void:
	book_series = ""
	for c in book_grid.get_children():
		c.queue_free()
	book_grid.columns = 2
	for g in _book_groups():
		var got := 0
		for c in g.items:
			if collection.has(c.id):
				got += 1
		var first: Dictionary = g.items[0]
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(0, 150)
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.icon = _art(str(first.get("art", "col_" + str(first.id))))
		btn.expand_icon = true
		btn.icon_alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.text = "%s
%d / %d" % [g.name, got, g.items.size()]
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.add_theme_font_size_override("font_size", 20)
		var bg := _box(Color(str(first.get("tint", "#d9c7a8"))).lerp(COL_PAPER, 0.55), 14)
		btn.add_theme_stylebox_override("normal", bg)
		btn.add_theme_stylebox_override("hover", bg)
		btn.add_theme_stylebox_override("pressed", bg)
		btn.add_theme_color_override("font_color", COL_INK)
		btn.add_theme_color_override("font_hover_color", COL_INK)
		if got == 0:
			btn.modulate = Color(1, 1, 1, 0.6)
		var series_name: String = g.name
		btn.pressed.connect(func() -> void: _show_book_items(series_name))
		book_grid.add_child(btn)
	book_count.text = "已收集 %d / %d　（收藏品跨局保留，点系列看详情）" % [collection.size(), gifts_data.collectibles.size()]
	book_close.text = "关闭"


## 第二层：一个系列里的每一件，没拿到的显示剪影和“？？？”
func _show_book_items(series: String) -> void:
	book_series = series
	for c in book_grid.get_children():
		c.queue_free()
	book_grid.columns = 4
	var got := 0
	for c in gifts_data.collectibles:
		if str(c.get("series", "其他")) != series:
			continue
		var have := collection.has(c.id)
		got += int(have)
		var cell := VBoxContainer.new()
		cell.custom_minimum_size = Vector2(140, 0)
		var icon := TextureRect.new()
		icon.custom_minimum_size = Vector2(120, 120)
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.texture = _art(str(c.get("art", "col_" + str(c.id))))
		if not have:
			icon.modulate = Color(0, 0, 0, 0.55)
		cell.add_child(icon)
		var cname := _label((str(c.name) + "
" + "★".repeat(int(c.rarity))) if have else "？？？", 16,
			COL_INK if have else COL_INK_SOFT, true)
		cname.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cell.add_child(cname)
		book_grid.add_child(cell)
	book_count.text = "%s　已收集 %d 件" % [series, got]
	book_close.text = "返回系列"


# ---------------- 存档 ----------------

func _save_game() -> void:
	var data := {"day": day, "cash": cash, "reputation": reputation, "inventory": inventory,
		"time_left": time_left, "order_tag": order_tag, "run_state": run_state,
		"collection": collection, "gift_queue": gift_queue, "gifts_today": gifts_today, "intel": intel,
		"settings": settings, "emergency_used": emergency_used, "extra_due": extra_due,
		"progress": progress.to_dict()}
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data))
		f.close()
	if _web:  # 电脑上也备份一份
		JavaScriptBridge.eval("window.parent.postMessage({type:'save',data:%s},location.origin)" % JSON.stringify(data), true)


## 读档成功返回 true。
func _load_game() -> bool:
	if not FileAccess.file_exists(SAVE_PATH):
		if _web:  # 手机上没有存档（换了网址或清了数据）：向电脑要备份
			JavaScriptBridge.eval("window.parent.postMessage({type:'need-save'},location.origin)", true)
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	return _apply_save(d)


## 用存档数据恢复进度。一局结束（输/赢）后只保留收藏品。
func _apply_save(d) -> bool:
	if typeof(d) != TYPE_DICTIONARY:
		return false
	collection = d.get("collection", {})
	progress.from_dict(d.get("progress"))
	settings = d.get("settings", settings)
	_apply_volume()
	gift_queue = d.get("gift_queue", [])
	intel = int(d.get("intel", 0))
	if str(d.get("run_state", "")) in ["lost", "won"]:
		return false
	day = int(d.get("day", 1))
	emergency_used = bool(d.get("emergency_used", false))
	extra_due = d.get("extra_due", {})
	cash = int(d.get("cash", tuning.start_cash))
	reputation = int(d.get("reputation", 0))
	inventory = d.get("inventory", [])
	gifts_today = int(d.get("gifts_today", 0))
	order_tag = str(d.get("order_tag", ""))
	time_left = int(d.get("time_left", _day_length()))
	if str(d.get("run_state", "")) == "day_end" or order_tag == "":
		_start_day()
		return true
	run_state = "playing"
	order_label.text = "今日订单：收购商高价收【%s】类，%.1f 倍" % [order_tag, float(tuning.order_bonus)]
	time_left += int(tuning.time_per_customer)  # 读档时重新来一位顾客，不额外扣时间
	_next_customer()
	_float_text("欢迎回来", COL_NEON)
	return true


# ---------------- 声音（由网页外壳播放，非 HTTPS 也能响） ----------------

func _sfx(sound: String) -> void:
	if _web:
		JavaScriptBridge.eval("window.parent.postMessage({type:'sfx',name:'%s'},location.origin)" % sound, true)


func _bgm(track: String) -> void:
	if _web:
		JavaScriptBridge.eval("window.parent.postMessage({type:'bgm',name:'%s'},location.origin)" % track, true)


func _art(art_name: String) -> Texture2D:
	var path := "res://assets/art/%s.png" % art_name
	if art_name != "" and ResourceLoader.exists(path):
		return load(path)
	return null


func _log(text: String, color: Color) -> void:
	log_label.text = text
	log_label.add_theme_color_override("font_color", color)


func _refresh() -> void:
	hud_day.text = "第 %d 天" % day
	hud_cash.text = "¥%d" % cash
	hud_rep.text = "口碑 %d" % reputation
	gift_btn.visible = not gift_queue.is_empty()
	gift_btn.text = "包裹 ×%d" % gift_queue.size()
	book_btn.text = "图鉴 %d/%d" % [collection.size(), gifts_data.collectibles.size()]
	var total := _day_length()
	progress.set_max("best_cash", cash)
	if time_pips.get_child_count() != total:
		for c in time_pips.get_children():
			c.queue_free()
		for i in total:
			var pip := Panel.new()
			pip.custom_minimum_size = Vector2(0, 14)
			pip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			time_pips.add_child(pip)
	for i in time_pips.get_child_count():
		var lit := i < time_left
		time_pips.get_child(i).add_theme_stylebox_override("panel",
			_box(COL_NEON if lit else Color("3a2f27"), 4))
	if not deal:
		return
	var pat_lit := ceili(clampf(deal.patience, 0, 100) / 20.0)
	for i in patience_pips.get_child_count():
		var col := COL_OK if pat_lit > 2 else (COL_NEON if pat_lit > 1 else COL_BAD)
		patience_pips.get_child(i).add_theme_stylebox_override("panel",
			_box(col if i < pat_lit else Color("3a2f27"), 4))
	ask_label.text = "要价\n¥%d" % deal.ask
	offer_label.text = "¥ %d" % offer_amount
	for i in round_pips.get_child_count():
		round_pips.get_child(i).add_theme_stylebox_override("panel",
			_box(COL_LCD if i < deal.rounds_left else Color("1f3a2b"), 6))
	take_btn.text = "按要价收  ¥%d" % deal.ask
	take_btn.disabled = not deal_open or deal.ask > cash
	for b in [offer_btn, refuse_btn, minus_btn, plus_btn]:
		b.disabled = not deal_open
	challenge_btn.disabled = not deal_open or deal.exposed
	for i in clue_box.get_child_count():
		var b: Button = clue_box.get_child(i)
		if i < deal.clues.size() and not deal.clues[i].revealed:
			b.disabled = not deal_open or (intel <= 0 and time_left < int(tuning.time_per_clue))
			b.get_meta("cost").text = ("情报 ×%d" % intel) if intel > 0 else ("耗时 %d" % int(tuning.time_per_clue))


# ---------------- 小动画 ----------------

func _pulse(c: Control) -> void:
	c.pivot_offset = c.size / 2
	var tw := create_tween().set_trans(Tween.TRANS_SINE)
	tw.tween_property(c, "scale", Vector2(1.08, 1.08), 0.08)
	tw.tween_property(c, "scale", Vector2.ONE, 0.12)


func _shake(c: Control) -> void:
	var x := c.position.x
	var tw := create_tween()
	for d in [10, -8, 6, -4, 0]:
		tw.tween_property(c, "position:x", x + d, 0.04)


# ---------------- 界面搭建 ----------------

func _build_ui() -> void:
	# 背景渐变
	var grad := Gradient.new()
	grad.set_color(0, COL_BG_TOP)
	grad.set_color(1, COL_BG_BOTTOM)
	var gtex := GradientTexture2D.new()
	gtex.gradient = grad
	gtex.fill_from = Vector2(0, 0)
	gtex.fill_to = Vector2(0, 1)
	var bg := TextureRect.new()
	bg.texture = gtex
	bg.stretch_mode = TextureRect.STRETCH_SCALE
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 22)
	margin.add_theme_constant_override("margin_right", 22)
	margin.add_theme_constant_override("margin_top", 18)
	margin.add_theme_constant_override("margin_bottom", 22)
	add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	margin.add_child(col)

	col.add_child(_build_hud())
	col.add_child(_build_scene())
	col.add_child(_build_ticket())

	log_label = _label("", 24, COL_MUTED, true)
	log_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	log_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	log_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	col.add_child(log_label)

	col.add_child(_build_register())

	float_layer = Control.new()
	float_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	float_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(float_layer)
	_build_result_layer()
	_build_home_layer()
	_build_dialog_layer()
	_build_settings_layer()
	_build_gift_layer()
	_build_book_layer()
	_build_pause_layer()


func _build_hud() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)

	var day_pill := PanelContainer.new()
	var sb := _box(Color(0, 0, 0, 0), 20)
	sb.border_color = COL_NEON
	sb.set_border_width_all(2)
	sb.content_margin_top = 4
	sb.content_margin_bottom = 4
	day_pill.add_theme_stylebox_override("panel", sb)
	hud_day = _label("", 24, COL_NEON)
	day_pill.add_child(hud_day)
	var home_btn := _button("主页", Color(0, 0, 0, 0), COL_TEXT, Color("4a3f36"))
	home_btn.custom_minimum_size = Vector2(0, 44)
	home_btn.add_theme_font_size_override("font_size", 20)
	home_btn.pressed.connect(_show_home)
	row.add_child(home_btn)
	row.add_child(day_pill)

	var sign_label := _label("待机回收站", 36, COL_NEON_PINK)
	sign_label.add_theme_constant_override("outline_size", 10)
	sign_label.add_theme_color_override("font_outline_color", Color(1, 0.42, 0.55, 0.25))
	sign_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sign_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# 窄屏放不下就省略标题，不能把整排撑宽（否则整页右边被切掉）
	sign_label.clip_text = true
	sign_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	row.add_child(sign_label)

	book_btn = _button("图鉴", Color(0, 0, 0, 0), COL_NEON, COL_NEON)
	book_btn.custom_minimum_size = Vector2(0, 44)
	book_btn.add_theme_font_size_override("font_size", 20)
	book_btn.pressed.connect(_open_book)
	row.add_child(book_btn)

	var cash_row := HBoxContainer.new()
	cash_row.add_theme_constant_override("separation", 8)
	var coin := Panel.new()
	coin.custom_minimum_size = Vector2(26, 26)
	coin.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var csb := _box(Color("f2c14e"), 13)
	csb.border_color = Color("b8862a")
	csb.set_border_width_all(3)
	coin.add_theme_stylebox_override("panel", csb)
	cash_row.add_child(coin)
	hud_cash = _label("", 28, COL_TEXT)
	cash_row.add_child(hud_cash)
	row.add_child(cash_row)
	box.add_child(row)

	var info_row := HBoxContainer.new()
	order_label = _label("", 20, COL_NEON)
	order_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	order_label.clip_text = true
	order_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	info_row.add_child(order_label)
	hud_rep = _label("", 20, COL_OK)
	info_row.add_child(hud_rep)
	box.add_child(info_row)

	var trow := HBoxContainer.new()
	trow.add_theme_constant_override("separation", 10)
	trow.add_child(_label("营业时间", 20, COL_MUTED))
	time_pips = HBoxContainer.new()
	time_pips.add_theme_constant_override("separation", 4)
	time_pips.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	time_pips.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	trow.add_child(time_pips)
	box.add_child(trow)
	return box


func _build_scene() -> Control:
	# 店铺场景：货架背景 + 顾客 + 对话气泡 + 柜台
	scene_panel = Control.new()
	scene_panel.custom_minimum_size = Vector2(0, 310)
	scene_panel.clip_contents = true
	scene_panel.draw.connect(_draw_scene_bg)

	shop_bg = TextureRect.new()
	shop_bg.texture = _art("shop_bg")
	shop_bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	shop_bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	shop_bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	shop_bg.modulate = Color(0.8, 0.75, 0.7)
	scene_panel.add_child(shop_bg)

	figure = Control.new()
	figure.custom_minimum_size = Vector2(230, 270)
	figure.size = Vector2(230, 270)
	figure.position = Vector2(16, 40)
	figure.draw.connect(_draw_figure)
	portrait = TextureRect.new()
	portrait.set_anchors_preset(Control.PRESET_FULL_RECT)
	portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	figure.add_child(portrait)
	scene_panel.add_child(figure)

	var name_box := VBoxContainer.new()
	name_box.position = Vector2(30, 6)
	name_box.add_theme_constant_override("separation", 4)
	name_label = _label("", 26, COL_TEXT)
	name_label.add_theme_constant_override("outline_size", 8)
	name_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	name_box.add_child(name_label)
	patience_pips = HBoxContainer.new()
	patience_pips.add_theme_constant_override("separation", 4)
	for i in 5:
		var p := Panel.new()
		p.custom_minimum_size = Vector2(26, 10)
		patience_pips.add_child(p)
	name_box.add_child(patience_pips)
	scene_panel.add_child(name_box)

	bubble = PanelContainer.new()
	var bsb := _box(COL_PAPER, 22)
	bsb.content_margin_left = 22
	bsb.content_margin_right = 22
	bsb.content_margin_top = 16
	bsb.content_margin_bottom = 16
	bsb.shadow_color = Color(0, 0, 0, 0.35)
	bsb.shadow_size = 8
	bubble.add_theme_stylebox_override("panel", bsb)
	bubble.anchor_left = 0.36
	bubble.anchor_right = 1.0
	bubble.offset_left = 0
	bubble.offset_right = -16
	bubble.offset_top = 40
	story_label = _label("", 26, COL_INK, true)
	bubble.add_child(story_label)
	scene_panel.add_child(bubble)

	var tail := Control.new()
	tail.anchor_left = 0.36
	tail.anchor_right = 0.36
	tail.offset_left = -18
	tail.offset_right = 6
	tail.offset_top = 70
	tail.custom_minimum_size = Vector2(24, 24)
	tail.draw.connect(func() -> void:
		tail.draw_colored_polygon(PackedVector2Array([Vector2(24, 0), Vector2(24, 26), Vector2(0, 20)]), COL_PAPER))
	scene_panel.add_child(tail)

	# 员工带回的包裹：放在柜台右下角，有包裹时才出现
	gift_btn = _button("包裹", COL_NEON, Color("1a1208"))
	gift_btn.custom_minimum_size = Vector2(170, 60)
	gift_btn.anchor_left = 1.0
	gift_btn.anchor_right = 1.0
	gift_btn.anchor_top = 1.0
	gift_btn.anchor_bottom = 1.0
	gift_btn.offset_left = -186
	gift_btn.offset_right = -16
	gift_btn.offset_top = -72
	gift_btn.offset_bottom = -12
	gift_btn.icon = _art("gift_small")
	gift_btn.expand_icon = true
	gift_btn.add_theme_constant_override("icon_max_width", 44)
	gift_btn.visible = false
	gift_btn.pressed.connect(_open_gift)
	scene_panel.add_child(gift_btn)
	return scene_panel


func _draw_scene_bg() -> void:
	var s := scene_panel.size
	var ci := scene_panel
	# 墙面与货架
	ci.draw_rect(Rect2(Vector2.ZERO, s), Color("1f1611"))
	var shelf_rng := RandomNumberGenerator.new()
	shelf_rng.seed = 7
	for row in 3:
		var y := 70.0 + row * 80.0
		ci.draw_rect(Rect2(0, y, s.x, 6), Color("3b2a1e"))
		var x := 8.0
		while x < s.x - 20:
			var w := shelf_rng.randf_range(18, 46)
			var h := shelf_rng.randf_range(20, 56)
			var c := Color.from_hsv(shelf_rng.randf(), 0.35, 0.32)
			ci.draw_rect(Rect2(x, y - h, w, h), c)
			x += w + shelf_rng.randf_range(6, 22)
	# 暖色灯光
	for i in 6:
		var a := 0.05 - i * 0.008
		ci.draw_circle(Vector2(s.x * 0.72, 0), 120 + i * 40, Color(1, 0.7, 0.3, maxf(a, 0.0)))
	# 柜台
	ci.draw_rect(Rect2(0, s.y - 56, s.x, 56), Color("5b3a24"))
	ci.draw_rect(Rect2(0, s.y - 56, s.x, 8), Color("8a5a36"))
	ci.draw_rect(Rect2(0, s.y - 8, s.x, 8), Color("3a2416"))


func _draw_figure() -> void:
	if portrait.texture != null:
		return  # 有美术图时用图片，否则用几何小人
	var c := figure_color
	var w := figure.size.x
	# 身体
	var body := StyleBoxFlat.new()
	body.bg_color = c.darkened(0.15)
	body.corner_radius_top_left = 70
	body.corner_radius_top_right = 70
	body.draw(figure.get_canvas_item(), Rect2(20, 120, w - 40, 140))
	# 头
	figure.draw_circle(Vector2(w / 2, 82), 50, c.lightened(0.25))
	figure.draw_circle(Vector2(w / 2 - 17, 78), 6, COL_INK)
	figure.draw_circle(Vector2(w / 2 + 17, 78), 6, COL_INK)
	figure.draw_arc(Vector2(w / 2, 96), 14, 0.3, PI - 0.3, 12, COL_INK, 3)
	# 胸牌
	var font := get_theme_default_font()
	figure.draw_string(font, Vector2(w / 2 - 15, 190), figure_initial, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, COL_TEXT)


func _build_ticket() -> Control:
	# 当票：旧纸色卡片，货物名 + 红色要价印章 + 鉴定线索
	ticket = PanelContainer.new()
	var tsb := _box(COL_PAPER, 14)
	tsb.content_margin_left = 22
	tsb.content_margin_right = 22
	tsb.content_margin_top = 18
	tsb.content_margin_bottom = 18
	tsb.border_color = COL_PAPER_DARK
	tsb.set_border_width_all(3)
	tsb.shadow_color = Color(0, 0, 0, 0.4)
	tsb.shadow_size = 10
	tsb.shadow_offset = Vector2(0, 4)
	ticket.add_theme_stylebox_override("panel", tsb)

	var tcol := VBoxContainer.new()
	tcol.add_theme_constant_override("separation", 10)
	var head := HBoxContainer.new()
	var title_col := VBoxContainer.new()
	title_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_col.add_theme_constant_override("separation", 0)
	title_col.add_child(_label("回 收 单", 18, COL_INK_SOFT))
	item_label = _label("", 34, COL_INK)
	title_col.add_child(item_label)
	tag_label = _label("", 20, COL_INK_SOFT)
	title_col.add_child(tag_label)
	item_icon = TextureRect.new()
	item_icon.custom_minimum_size = Vector2(96, 96)
	item_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	item_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	item_icon.visible = false
	head.add_child(item_icon)
	head.add_theme_constant_override("separation", 12)
	head.add_child(title_col)

	ask_stamp = PanelContainer.new()
	var ssb := _box(Color(0, 0, 0, 0), 8)
	ssb.border_color = COL_STAMP
	ssb.set_border_width_all(3)
	ssb.content_margin_top = 6
	ssb.content_margin_bottom = 6
	ask_stamp.add_theme_stylebox_override("panel", ssb)
	ask_stamp.rotation_degrees = -6
	ask_stamp.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ask_label = _label("", 24, COL_STAMP)
	ask_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	ask_stamp.add_child(ask_label)
	head.add_child(ask_stamp)
	tcol.add_child(head)

	var line := ColorRect.new()
	line.color = COL_PAPER_DARK
	line.custom_minimum_size = Vector2(0, 2)
	tcol.add_child(line)

	clue_box = VBoxContainer.new()
	clue_box.add_theme_constant_override("separation", 8)
	tcol.add_child(clue_box)

	challenge_btn = _button("质疑来历：“这东西真是你的？”", Color(0, 0, 0, 0), COL_STAMP, COL_STAMP)
	challenge_btn.custom_minimum_size = Vector2(0, 62)
	tcol.add_child(challenge_btn)
	challenge_btn.pressed.connect(_on_challenge)
	ticket.add_child(tcol)
	return ticket


func _clue_button(text: String, cost: String) -> Button:
	var b := Button.new()
	b.text = text
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	b.custom_minimum_size = Vector2(0, 60)
	b.add_theme_font_size_override("font_size", 24)
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		b.add_theme_color_override(state, COL_INK)
	b.add_theme_color_override("font_disabled_color", COL_INK_SOFT)
	var normal := _box(COL_PAPER_DARK.lightened(0.15), 10)
	normal.border_color = COL_INK_SOFT
	normal.set_border_width_all(2)
	b.add_theme_stylebox_override("normal", normal)
	b.add_theme_stylebox_override("hover", normal)
	b.add_theme_stylebox_override("focus", normal)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = COL_PAPER_DARK
	b.add_theme_stylebox_override("pressed", pressed)
	var dis := normal.duplicate() as StyleBoxFlat
	dis.bg_color = COL_PAPER_DARK.darkened(0.05)
	dis.border_color = COL_PAPER_DARK
	b.add_theme_stylebox_override("disabled", dis)
	var tag := _label(cost, 18, COL_INK_SOFT)
	tag.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	tag.offset_left = -84
	tag.offset_right = -14
	tag.offset_top = -12
	tag.offset_bottom = 12
	tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	b.add_child(tag)
	b.set_meta("cost", tag)
	return b


func _revealed_box() -> StyleBoxFlat:
	var sb := _box(Color("fff6e3"), 10)
	sb.border_color = COL_NEON
	sb.border_width_left = 6
	return sb


func _build_register() -> Control:
	# 收银机：液晶出价屏 + 加减 + 出价 + 两个次要按钮
	var reg := PanelContainer.new()
	var rsb := _box(COL_METAL, 22)
	rsb.border_color = Color("3a312a")
	rsb.border_width_top = 4
	rsb.content_margin_left = 18
	rsb.content_margin_right = 18
	rsb.content_margin_top = 18
	rsb.content_margin_bottom = 18
	rsb.shadow_color = Color(0, 0, 0, 0.5)
	rsb.shadow_size = 12
	reg.add_theme_stylebox_override("panel", rsb)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)

	var lcd_row := HBoxContainer.new()
	lcd_row.add_theme_constant_override("separation", 12)
	minus_btn = _round_button("－")
	minus_btn.pressed.connect(_change_offer.bind(-1))
	lcd_row.add_child(minus_btn)

	var lcd := PanelContainer.new()
	lcd.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var lsb := _box(COL_LCD_BG, 12)
	lsb.border_color = Color("24402f")
	lsb.set_border_width_all(2)
	lsb.content_margin_top = 8
	lsb.content_margin_bottom = 8
	lcd.add_theme_stylebox_override("panel", lsb)
	var lcd_col := VBoxContainer.new()
	lcd_col.add_theme_constant_override("separation", 2)
	var lcd_top := HBoxContainer.new()
	var lcd_title := _label("你的出价", 18, COL_LCD.darkened(0.35))
	lcd_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lcd_top.add_child(lcd_title)
	round_pips = HBoxContainer.new()
	round_pips.add_theme_constant_override("separation", 5)
	round_pips.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	for i in int(tuning.haggle_rounds):
		var p := Panel.new()
		p.custom_minimum_size = Vector2(14, 14)
		round_pips.add_child(p)
	lcd_top.add_child(round_pips)
	lcd_col.add_child(lcd_top)
	offer_label = _label("", 46, COL_LCD)
	offer_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	offer_label.add_theme_constant_override("outline_size", 6)
	offer_label.add_theme_color_override("font_outline_color", Color(0.49, 1, 0.7, 0.18))
	lcd_col.add_child(offer_label)
	lcd.add_child(lcd_col)
	lcd_row.add_child(lcd)

	plus_btn = _round_button("＋")
	plus_btn.pressed.connect(_change_offer.bind(1))
	lcd_row.add_child(plus_btn)
	col.add_child(lcd_row)

	# 快捷出价：减少反复点加减（《深空当铺》玩家最常抱怨的就是点太多）
	var chips := HBoxContainer.new()
	chips.add_theme_constant_override("separation", 10)
	for r in tuning.quick_offer_ratios:
		var chip := _button("%d 成" % roundi(float(r) * 10), Color("2e2722"), COL_LCD, Color("24402f"))
		chip.custom_minimum_size = Vector2(0, 56)
		chip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		chip.add_theme_font_size_override("font_size", 24)
		chip.pressed.connect(_on_quick_offer.bind(float(r)))
		chips.add_child(chip)
	col.add_child(chips)

	offer_btn = _button("出 价", COL_NEON, Color("1a1208"))
	offer_btn.custom_minimum_size = Vector2(0, 84)
	offer_btn.add_theme_font_size_override("font_size", 32)
	offer_btn.pressed.connect(_on_offer)
	col.add_child(offer_btn)

	var brow := HBoxContainer.new()
	brow.add_theme_constant_override("separation", 12)
	take_btn = _button("", Color(0, 0, 0, 0), COL_OK, COL_OK)
	take_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	take_btn.pressed.connect(_on_take)
	refuse_btn = _button("不收了", Color(0, 0, 0, 0), COL_BAD, COL_BAD)
	refuse_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	refuse_btn.pressed.connect(_on_refuse)
	brow.add_child(take_btn)
	brow.add_child(refuse_btn)
	col.add_child(brow)
	reg.add_child(col)
	return reg


func _build_result_layer() -> void:
	result_layer = ColorRect.new()
	(result_layer as ColorRect).color = Color(0.03, 0.02, 0.02, 0.82)
	result_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	result_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	result_card = PanelContainer.new()
	result_card.custom_minimum_size = Vector2(600, 0)
	var sb := _box(COL_PAPER, 22)
	sb.content_margin_left = 34
	sb.content_margin_right = 34
	sb.content_margin_top = 30
	sb.content_margin_bottom = 30
	sb.shadow_color = Color(0, 0, 0, 0.5)
	sb.shadow_size = 20
	result_card.add_theme_stylebox_override("panel", sb)
	var rcol := VBoxContainer.new()
	rcol.add_theme_constant_override("separation", 16)
	result_title = _label("", 30, COL_INK_SOFT)
	result_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	result_big = _label("", 72, COL_OK)
	result_big.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	result_label = _label("", 26, COL_INK, true)
	result_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	result_btn = _button("下一位顾客", COL_NEON, Color("1a1208"))
	result_btn.custom_minimum_size = Vector2(0, 80)
	result_btn.pressed.connect(_on_result_next)
	result_btn2 = _button("从头再来", Color(0, 0, 0, 0), COL_INK, COL_INK_SOFT)
	result_btn2.custom_minimum_size = Vector2(0, 64)
	result_btn2.pressed.connect(func() -> void:
		result_layer.visible = false
		result_btn2.visible = false
		_restart())
	result_btn2.visible = false
	rcol.add_child(result_title)
	rcol.add_child(result_big)
	rcol.add_child(result_label)
	rcol.add_child(result_btn)
	rcol.add_child(result_btn2)
	result_card.add_child(rcol)
	center.add_child(result_card)
	result_layer.add_child(center)
	result_layer.visible = false
	add_child(result_layer)


func _build_gift_layer() -> void:
	gift_layer = ColorRect.new()
	gift_layer.color = Color(0.03, 0.02, 0.02, 0.86)
	gift_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	gift_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(600, 0)
	var sb := _box(COL_PAPER, 22)
	sb.content_margin_left = 30
	sb.content_margin_right = 30
	sb.content_margin_top = 26
	sb.content_margin_bottom = 26
	card.add_theme_stylebox_override("panel", sb)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 14)
	gift_title = _label("", 30, COL_INK_SOFT)
	gift_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	gift_art = TextureRect.new()
	gift_art.custom_minimum_size = Vector2(0, 260)
	gift_art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	gift_art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	gift_body = _label("", 26, COL_INK, true)
	gift_body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	gift_action = _button("拆开", COL_NEON, Color("1a1208"))
	gift_action.custom_minimum_size = Vector2(0, 80)
	gift_action.pressed.connect(_on_gift_action)
	for c in [gift_title, gift_art, gift_body, gift_action]:
		col.add_child(c)
	card.add_child(col)
	center.add_child(card)
	gift_layer.add_child(center)
	gift_layer.visible = false
	add_child(gift_layer)


func _build_book_layer() -> void:
	book_layer = ColorRect.new()
	book_layer.color = Color(0.03, 0.02, 0.02, 0.9)
	book_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	book_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 30)
	var card := PanelContainer.new()
	var sb := _box(COL_PAPER, 22)
	sb.content_margin_top = 20
	sb.content_margin_bottom = 20
	card.add_theme_stylebox_override("panel", sb)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	var title := _label("收藏图鉴", 34, COL_INK)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(title)
	book_count = _label("", 20, COL_INK_SOFT)
	book_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(book_count)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	book_grid = GridContainer.new()
	book_grid.columns = 4
	book_grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	book_grid.add_theme_constant_override("h_separation", 6)
	book_grid.add_theme_constant_override("v_separation", 14)
	scroll.add_child(book_grid)
	col.add_child(scroll)
	book_close = _button("关闭", COL_NEON, Color("1a1208"))
	book_close.pressed.connect(func() -> void:
		if book_series != "":
			_show_book_series()
		else:
			book_layer.visible = false)
	col.add_child(book_close)
	card.add_child(col)
	margin.add_child(card)
	book_layer.add_child(margin)
	book_layer.visible = false
	add_child(book_layer)


func _build_pause_layer() -> void:
	# 暂停层：外壳处理真实请求时盖住游戏，挡住所有点击
	pause_layer = ColorRect.new()
	pause_layer.color = Color(0.02, 0.015, 0.01, 0.8)
	pause_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	pause_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	pause_label = _label("暂停中", 32, COL_NEON, true)
	pause_label.set_anchors_preset(Control.PRESET_FULL_RECT)
	pause_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	pause_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	pause_label.add_theme_constant_override("outline_size", 10)
	pause_label.add_theme_color_override("font_outline_color", Color(1, 0.7, 0.28, 0.2))
	pause_layer.add_child(pause_label)
	pause_layer.visible = false
	add_child(pause_layer)


# ---------------- 控件工厂 ----------------

func _label(text: String, size: int, color: Color, wrap := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


func _button(text: String, color: Color, font_color: Color = COL_TEXT, border := Color(0, 0, 0, 0)) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 70)
	b.add_theme_font_size_override("font_size", 26)
	for state in ["font_color", "font_pressed_color", "font_hover_color", "font_focus_color"]:
		b.add_theme_color_override(state, font_color)
	b.add_theme_color_override("font_disabled_color", font_color.darkened(0.5))
	var normal := _box(color, 14)
	if border.a > 0:
		normal.border_color = border
		normal.set_border_width_all(2)
	b.add_theme_stylebox_override("normal", normal)
	b.add_theme_stylebox_override("focus", normal)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = color.lightened(0.08) if color.a > 0 else Color(border.r, border.g, border.b, 0.08)
	b.add_theme_stylebox_override("hover", hover)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = color.darkened(0.15) if color.a > 0 else Color(border.r, border.g, border.b, 0.18)
	b.add_theme_stylebox_override("pressed", pressed)
	var dis := normal.duplicate() as StyleBoxFlat
	dis.bg_color = color.darkened(0.45) if color.a > 0 else Color(0, 0, 0, 0)
	dis.border_color = border.darkened(0.5)
	b.add_theme_stylebox_override("disabled", dis)
	return b


func _round_button(text: String) -> Button:
	var b := _button(text, Color("2e2722"), COL_TEXT, Color("4a3f36"))
	b.custom_minimum_size = Vector2(84, 84)
	b.add_theme_font_size_override("font_size", 38)
	for key in ["normal", "hover", "pressed", "focus", "disabled"]:
		var sb := b.get_theme_stylebox(key).duplicate() as StyleBoxFlat
		sb.set_corner_radius_all(42)
		b.add_theme_stylebox_override(key, sb)
	return b


func _box(color: Color, radius: int) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	sb.anti_aliasing = true
	return sb


func _load_json(path: String) -> Dictionary:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}

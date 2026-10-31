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
var items: Array
var customers: Array
var rng := RandomNumberGenerator.new()

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

var _web := false
var _poll := 0.0


func _ready() -> void:
	tuning = _load_json("res://data/tuning.json")
	var data := _load_json("res://data/items.json")
	items = data.items
	customers = data.customers
	rng.randomize()
	cash = int(tuning.start_cash)
	time_left = int(tuning.time_per_day)
	_build_ui()
	_web = OS.has_feature("web")
	if _web:
		JavaScriptBridge.eval("""
			window.__ssq = [];
			window.addEventListener('message', function (e) {
				if (e.origin === location.origin && e.data && e.data.type) window.__ssq.push(e.data);
			});
			if (window.parent !== window) window.parent.postMessage({type: 'game-ready'}, location.origin);
		""", true)
	_next_customer()


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
		"employee":
			var who := "Claude 员工" if m.get("agent", "") == "claude" else "Codex 员工"
			var kind := str(m.get("kind", ""))
			if kind == "approval":
				pause_label.text = "%s推门进来\n“老板，有件事要你拍板。”\n\n生意会原样等你回来" % who
			elif kind == "done":
				pause_label.text = "%s回来汇报了" % who
			else:
				pause_label.text = "%s发来消息" % who
			_show_pause(true)


func _show_pause(on: bool) -> void:
	if on == pause_layer.visible:
		return
	pause_layer.visible = on
	if on:
		pause_layer.modulate.a = 0.0
		create_tween().tween_property(pause_layer, "modulate:a", 1.0, 0.2)


# ---------------- 流程 ----------------

func _next_customer() -> void:
	if time_left < int(tuning.time_per_customer) + 1:
		_end_day()
		return
	time_left -= int(tuning.time_per_customer)
	deal = Deal.new(tuning, items, customers, rng)
	deal_open = true
	offer_amount = clampi(roundi(deal.ask * float(tuning.offer_start_ratio) / 10.0) * 10, 10, cash)
	figure_color = CUSTOMER_COLORS[customers.find(deal.customer) % CUSTOMER_COLORS.size()]
	figure_initial = deal.customer.substr(0, 1)
	figure.queue_redraw()
	name_label.text = deal.customer
	story_label.text = "“%s”" % deal.story
	item_label.text = deal.item.name
	_log("%s 把一件%s放在柜台上。" % [deal.customer, deal.item.name], COL_MUTED)
	_build_clues()
	_refresh()
	_animate_arrival()


func _animate_arrival() -> void:
	figure.modulate.a = 0.0
	figure.position = Vector2(146, 52)
	bubble.modulate.a = 0.0
	ticket.modulate.a = 0.0
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(figure, "position:x", 26.0, 0.35)
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


func _on_clue(i: int, b: Button) -> void:
	if not deal_open or deal.clues[i].revealed:
		return
	if time_left < int(tuning.time_per_clue):
		_log("今天没时间细看了。", COL_BAD)
		return
	time_left -= int(tuning.time_per_clue)
	var text := deal.reveal(i)
	b.text = "✓  " + text
	b.disabled = true
	b.add_theme_stylebox_override("disabled", _revealed_box())
	b.add_theme_color_override("font_disabled_color", COL_INK)
	b.get_meta("cost").visible = false
	_pulse(b)
	_refresh()


func _on_challenge() -> void:
	if not deal_open or deal.challenged:
		return
	var r := deal.challenge()
	_log(r.text, COL_OK if r.mood == "caught" else COL_BAD)
	if r.mood == "caught":
		_pulse(ask_stamp)
	else:
		_shake(figure)
	if deal.patience <= 0:
		_close_deal(false, "顾客扭头就走了。")
		return
	offer_amount = mini(offer_amount, deal.ask)
	_refresh()


func _on_offer() -> void:
	if not deal_open:
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
			_shake(figure)
			_pulse(ask_stamp)
			_refresh()


func _on_take() -> void:
	if deal_open and deal.ask <= cash:
		_buy(deal.ask)


func _on_refuse() -> void:
	if deal_open:
		_close_deal(false, "你摆摆手，%s 带着%s走了。" % [deal.customer, deal.item.name])


func _buy(price: int) -> void:
	cash -= price
	inventory.append({"name": deal.item.name, "paid": price, "value": deal.true_value,
		"leaky": deal.item.get("leaky", false)})
	var p := deal.profit(price)
	var lines := ["%s　付出 ¥%d" % [deal.item.name, price], "收购商估价 ¥%d" % deal.true_value]
	if deal.lying:
		lines.append("顾客说了谎：%s" % _lie_text())
	if deal.item.get("leaky", false):
		lines.append("注意：这是会漏液的问题货")
	_show_result("成交", ("+¥%d" % p) if p >= 0 else ("-¥%d" % -p), COL_OK if p >= 0 else COL_BAD,
		"\n".join(lines))


func _lie_text() -> String:
	for c in deal.clues:
		if c.is_lie:
			return "%s%s" % [c.part, c.text]
	return ""


func _close_deal(_bought: bool, text: String) -> void:
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
	result_layer.visible = true
	result_layer.modulate.a = 0.0
	result_card.scale = Vector2(0.85, 0.85)
	result_card.pivot_offset = result_card.size / 2
	var tw := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(result_layer, "modulate:a", 1.0, 0.15)
	tw.parallel().tween_property(result_card, "scale", Vector2.ONE, 0.3)


func _on_result_next() -> void:
	result_layer.visible = false
	_next_customer()


func _end_day() -> void:
	var total := 0
	var paid := 0
	for it in inventory:
		total += int(it.value)
		paid += int(it.paid)
	cash += total
	var net := total - paid
	result_title.text = "第 %d 天 打烊" % day
	result_big.text = ("+¥%d" % net) if net >= 0 else ("-¥%d" % -net)
	result_big.add_theme_color_override("font_color", COL_OK if net >= 0 else COL_BAD)
	result_label.text = "收了 %d 件货，花了 ¥%d\n收购商一共付了 ¥%d\n\n现金 ¥%d" % [inventory.size(), paid, total, cash]
	inventory.clear()
	day += 1
	time_left = int(tuning.time_per_day)
	result_btn.text = "开始第 %d 天" % day
	deal_open = false
	_open_result()
	_refresh()


func _change_offer(sign_dir: int) -> void:
	var step := maxi(10, roundi(deal.ask * float(tuning.offer_step_ratio) / 10.0) * 10)
	offer_amount = clampi(offer_amount + sign_dir * step, 10, mini(cash, deal.ask))
	_refresh()
	_pulse(offer_label)


func _log(text: String, color: Color) -> void:
	log_label.text = text
	log_label.add_theme_color_override("font_color", color)


func _refresh() -> void:
	hud_day.text = "第 %d 天" % day
	hud_cash.text = "¥%d" % cash
	var total := int(tuning.time_per_day)
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
	challenge_btn.disabled = not deal_open or deal.challenged
	for i in clue_box.get_child_count():
		var b: Button = clue_box.get_child(i)
		if i < deal.clues.size() and not deal.clues[i].revealed:
			b.disabled = not deal_open or time_left < int(tuning.time_per_clue)


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
	_build_result_layer()
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
	row.add_child(day_pill)

	var sign_label := _label("待机回收站", 36, COL_NEON_PINK)
	sign_label.add_theme_constant_override("outline_size", 10)
	sign_label.add_theme_color_override("font_outline_color", Color(1, 0.42, 0.55, 0.25))
	sign_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sign_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(sign_label)

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
	scene_panel.custom_minimum_size = Vector2(0, 330)
	scene_panel.clip_contents = true
	scene_panel.draw.connect(_draw_scene_bg)

	figure = Control.new()
	figure.custom_minimum_size = Vector2(180, 250)
	figure.size = Vector2(180, 250)
	figure.position = Vector2(26, 52)
	figure.draw.connect(_draw_figure)
	scene_panel.add_child(figure)

	var name_box := VBoxContainer.new()
	name_box.position = Vector2(30, 6)
	name_box.add_theme_constant_override("separation", 4)
	name_label = _label("", 26, COL_TEXT)
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
	rcol.add_child(result_title)
	rcol.add_child(result_big)
	rcol.add_child(result_label)
	rcol.add_child(result_btn)
	result_card.add_child(rcol)
	center.add_child(result_card)
	result_layer.add_child(center)
	result_layer.visible = false
	add_child(result_layer)


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

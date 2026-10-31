class_name MetaUI
extends Control
## 长期进度的界面：店铺升级、抽员工造型、成就页、成就解锁弹窗、给员工换造型。
## 规则在 progress.gd；钱、存档、音效、控件样式借用 main.gd（game）。

const COL_PAPER := Color("efe1c6")
const COL_PAPER_DARK := Color("d9c6a3")
const COL_INK := Color("3a2618")
const COL_INK_SOFT := Color("7a5d44")
const COL_NEON := Color("ffb347")
const COL_OK := Color("2e9b5f")
const COL_BAD := Color("c8372d")

var game                     ## main.gd
var progress: Progress
var _layer: ColorRect        ## 当前打开的面板（同一时间只开一个）
var _toast_queue: Array = []
var _toast_busy := false
var _toast_layer: CanvasLayer  ## 成就弹窗放在最上层，不会被面板挡住


func setup(p_game, p_progress: Progress) -> void:
	game = p_game
	progress = p_progress
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)  # 铺满全屏（只设锚点不会撑开大小）
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	progress.achievement_unlocked.connect(_on_achievement)
	_toast_layer = CanvasLayer.new()
	_toast_layer.layer = 50
	add_child(_toast_layer)


# ---------------- 通用：一张纸卡片面板 ----------------

## 打开一个面板，返回 [内容列, 标题副标签]。内容放进可滚动区域。
func _open_panel(title: String) -> Array:
	close_panel()
	_layer = ColorRect.new()
	_layer.color = Color(0.03, 0.02, 0.02, 0.9)
	_layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 24)
	var card := PanelContainer.new()
	var sb: StyleBoxFlat = game._box(COL_PAPER, 22)
	sb.content_margin_left = 22
	sb.content_margin_right = 22
	sb.content_margin_top = 20
	sb.content_margin_bottom = 20
	card.add_theme_stylebox_override("panel", sb)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	var t: Label = game._label(title, 34, COL_INK)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(t)
	var sub: Label = game._label("", 20, COL_INK_SOFT, true)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(sub)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 12)
	scroll.add_child(body)
	col.add_child(scroll)
	var close: Button = game._button("关闭", COL_NEON, Color("1a1208"))
	close.custom_minimum_size = Vector2(0, 64)
	close.pressed.connect(close_panel)
	col.add_child(close)
	card.add_child(col)
	margin.add_child(card)
	_layer.add_child(margin)
	add_child(_layer)
	game._sfx("tap")
	return [body, sub]


func close_panel() -> void:
	if _layer:
		_layer.queue_free()
		_layer = null
	game._refresh()


func _row_box(bg: Color) -> PanelContainer:
	var p := PanelContainer.new()
	var sb: StyleBoxFlat = game._box(bg, 14)
	sb.content_margin_left = 16
	sb.content_margin_right = 16
	sb.content_margin_top = 12
	sb.content_margin_bottom = 12
	p.add_theme_stylebox_override("panel", sb)
	return p


func _cash_line() -> String:
	var due: Vector2i = game._next_due(game.day)
	var s := "现金 ¥%d" % game.cash
	if due.x > 0:
		s += "　·　第 %d 天要还贷 ¥%d，别花光了" % [due.x, due.y]
	return s


# ---------------- 店铺升级 ----------------

func open_upgrades() -> void:
	var parts := _open_panel("店铺升级")
	var body: VBoxContainer = parts[0]
	parts[1].text = _cash_line() + "\n升级永久保留，换一局也在。"
	for u in progress.meta.upgrades:
		var lv := progress.level(u.id)
		var maxed: bool = lv >= u.levels.size()
		var row := _row_box(COL_PAPER_DARK if not maxed else Color("e6d9b8"))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 14)
		var icon: Label = game._label(str(u.icon), 44, COL_INK)
		h.add_child(icon)
		var v := VBoxContainer.new()
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		v.add_child(game._label("%s　%s" % [u.name, "★".repeat(lv) + "☆".repeat(u.levels.size() - lv)], 26, COL_INK))
		v.add_child(game._label(str(u.desc), 18, COL_INK_SOFT, true))
		var now_text: String = "现在：" + (str(u.levels[lv - 1].text) if lv > 0 else "还没买")
		v.add_child(game._label(now_text, 18, COL_OK if lv > 0 else COL_INK_SOFT, true))
		if not maxed:
			v.add_child(game._label("下一级：" + str(u.levels[lv].text), 18, COL_INK, true))
		h.add_child(v)
		var cost := progress.next_cost(u.id)
		var b: Button = game._button("已满级" if maxed else "¥%d" % cost, COL_NEON if not maxed else Color("cbbd9c"), Color("1a1208"))
		b.custom_minimum_size = Vector2(130, 64)
		b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		b.disabled = maxed or game.cash < cost
		var id: String = u.id
		b.pressed.connect(func() -> void:
			if game.cash < progress.next_cost(id):
				return
			game.cash -= progress.next_cost(id)
			progress.buy_upgrade(id)
			game._sfx("coin")
			game._float_text("%s 升到 %d 级" % [progress.upgrade_def(id).name, progress.level(id)], Color("4cd18a"))
			game._save_game()
			open_upgrades())
		h.add_child(b)
		row.add_child(h)
		body.add_child(row)


# ---------------- 抽员工造型 ----------------

func open_gacha() -> void:
	var g: Dictionary = progress.meta.gacha
	var parts := _open_panel("抽员工造型")
	var body: VBoxContainer = parts[0]
	parts[1].text = "%s\n已拥有 %d / %d 个造型　·　重复的退 ¥%d　·　拥有的造型可以给任何员工换上" % [
		_cash_line(), progress.skins.size(), g.skins.size(), int(g.dupe_refund)]
	var odds := []
	var total := 0.0
	for r in g.rarities:
		total += float(r.weight)
	for r in g.rarities:
		odds.append("%s %d%%" % [r.name, roundi(float(r.weight) / total * 100)])
	body.add_child(game._label("概率：" + "　".join(odds), 18, COL_INK_SOFT, true))
	var btns := HBoxContainer.new()
	btns.add_theme_constant_override("separation", 12)
	for n in [1, 10]:
		var cost := int(g.cost) if n == 1 else int(g.ten_cost)
		var b: Button = game._button("抽 %d 次　¥%d" % [n, cost], COL_NEON, Color("1a1208"))
		b.custom_minimum_size = Vector2(0, 70)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.disabled = game.cash < cost
		var count: int = n
		b.pressed.connect(func() -> void: _do_draw(count))
		btns.add_child(b)
	body.add_child(btns)
	body.add_child(_skin_grid(func(_look): pass, false))


## 所有造型的格子：拥有的亮，没有的是剪影。pickable 时点击会回调 on_pick(look)。
func _skin_grid(on_pick: Callable, only_owned: bool) -> GridContainer:
	var grid := GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 10)
	for s in progress.meta.gacha.skins:
		var have := progress.skins.has(s.look)
		if only_owned and not have:
			continue
		var r := progress.rarity_def(s.rarity)
		var cell := VBoxContainer.new()
		cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var frame := PanelContainer.new()
		var fsb: StyleBoxFlat = game._box(Color(1, 1, 1, 0.35), 12)
		fsb.border_color = Color(str(r.color))
		fsb.set_border_width_all(3)
		frame.add_theme_stylebox_override("panel", fsb)
		var pic := TextureRect.new()
		pic.custom_minimum_size = Vector2(0, 150)
		pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		pic.texture = game._art(str(s.look))
		if not have:
			pic.modulate = Color(0, 0, 0, 0.5)
		frame.add_child(pic)
		cell.add_child(frame)
		var name_l: Label = game._label("%s\n%s" % [s.name if have else "？？？", r.name], 16, COL_INK if have else COL_INK_SOFT, true)
		name_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cell.add_child(name_l)
		if only_owned:
			var look: String = s.look
			frame.mouse_filter = Control.MOUSE_FILTER_STOP
			frame.gui_input.connect(func(ev: InputEvent) -> void:
				if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
					on_pick.call(look))
		grid.add_child(cell)
	return grid


func _do_draw(n: int) -> void:
	var g: Dictionary = progress.meta.gacha
	var cost := int(g.cost) if n == 1 else int(g.ten_cost)
	if game.cash < cost:
		return
	game.cash -= cost
	var results := progress.draw(n, game.rng)
	for r in results:
		game.cash += int(r.refund)
	game._save_game()
	_show_draw_results(results)


## 抽卡结果：卡片一张张翻出来，稀有度越高边框越亮
func _show_draw_results(results: Array) -> void:
	var parts := _open_panel("抽到了！")
	var body: VBoxContainer = parts[0]
	var new_count := results.filter(func(r): return r.fresh).size()
	var refund := 0
	for r in results:
		refund += int(r.refund)
	parts[1].text = "新造型 %d 个%s" % [new_count, ("　·　重复的退回 ¥%d" % refund) if refund > 0 else ""]
	var grid := GridContainer.new()
	grid.columns = 2 if results.size() == 1 else 5
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 10)
	var best := "n"
	var order := ["n", "r", "sr", "ssr"]
	var i := 0
	for r in results:
		var s: Dictionary = r.skin
		if order.find(s.rarity) > order.find(best):
			best = s.rarity
		var rar := progress.rarity_def(s.rarity)
		var cell := VBoxContainer.new()
		cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var frame := PanelContainer.new()
		var fsb: StyleBoxFlat = game._box(Color(str(rar.color)).lerp(COL_PAPER, 0.6), 12)
		fsb.border_color = Color(str(rar.color))
		fsb.set_border_width_all(4)
		frame.add_theme_stylebox_override("panel", fsb)
		var pic := TextureRect.new()
		pic.custom_minimum_size = Vector2(0, 260 if results.size() == 1 else 130)
		pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		pic.texture = game._art(str(s.look))
		frame.add_child(pic)
		cell.add_child(frame)
		var tag: Label = game._label("%s%s\n%s" % ["NEW " if r.fresh else "", s.name, rar.name], 16,
			Color(str(rar.color)).darkened(0.25), true)
		tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cell.add_child(tag)
		# 一张张翻出来
		cell.modulate.a = 0.0
		cell.scale = Vector2(0.7, 0.7)
		var tw := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
		tw.tween_interval(0.12 * i)
		tw.tween_property(cell, "modulate:a", 1.0, 0.15)
		tw.parallel().tween_property(cell, "scale", Vector2.ONE, 0.3)
		grid.add_child(cell)
		i += 1
	body.add_child(grid)
	var again: Button = game._button("再抽", Color("cbbd9c"), Color("1a1208"))
	again.custom_minimum_size = Vector2(0, 60)
	again.pressed.connect(open_gacha)
	body.add_child(again)
	game._sfx("win" if best == "ssr" else "gift")


## 给员工换造型：只能选已经拥有的
func open_skin_picker(employee: Dictionary, on_pick: Callable) -> void:
	var parts := _open_panel("给 %s 换造型" % str(employee.get("name", "员工")))
	parts[1].text = "只显示你拥有的造型。想要更多：主页 →「抽造型」"
	var pick := func(look: String) -> void:
		close_panel()
		on_pick.call(look)
	parts[0].add_child(_skin_grid(pick, true))


# ---------------- 成就 ----------------

func open_achievements() -> void:
	var parts := _open_panel("成就")
	var body: VBoxContainer = parts[0]
	var all: Array = progress.meta.achievements
	parts[1].text = "已解锁 %d / %d" % [progress.ach.size(), all.size()]
	var sorted := all.duplicate()
	sorted.sort_custom(func(a, b): return int(progress.ach.has(a.id)) > int(progress.ach.has(b.id)))
	for a in sorted:
		var got := progress.ach.has(a.id)
		var hidden := bool(a.get("hidden", false)) and not got
		var row := _row_box(Color("f6e7c2") if got else COL_PAPER_DARK)
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 14)
		h.add_child(game._label("★" if got else "☆", 40, COL_NEON if got else COL_INK_SOFT))
		var v := VBoxContainer.new()
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		v.add_child(game._label("？？？（隐藏成就）" if hidden else str(a.name), 24, COL_INK if got else COL_INK_SOFT))
		v.add_child(game._label("继续玩，总会发现的。" if hidden else str(a.desc), 18, COL_INK_SOFT, true))
		if got:
			var t := Time.get_datetime_dict_from_unix_time(int(progress.ach[a.id]))
			v.add_child(game._label("解锁于 %d 月 %d 日" % [t.month, t.day], 16, COL_OK))
		elif not hidden:
			var cur := mini(int(progress.stats.get(a.stat, 0)), int(a.goal))
			var bar := ProgressBar.new()
			bar.max_value = float(a.goal)
			bar.value = float(cur)
			bar.show_percentage = false
			bar.custom_minimum_size = Vector2(0, 14)
			bar.add_theme_stylebox_override("background", game._box(Color("c9b48d"), 7))
			bar.add_theme_stylebox_override("fill", game._box(COL_NEON, 7))
			v.add_child(bar)
			v.add_child(game._label("%d / %d" % [cur, int(a.goal)], 16, COL_INK_SOFT))
		h.add_child(v)
		row.add_child(h)
		if not got:
			row.modulate = Color(1, 1, 1, 0.8)
		body.add_child(row)


## 解锁弹窗：右上角滑进来，停 3 秒，排队一个个弹
func _on_achievement(a: Dictionary) -> void:
	_toast_queue.append(a)
	if not _toast_busy:
		_next_toast()


func _next_toast() -> void:
	if _toast_queue.is_empty():
		_toast_busy = false
		return
	_toast_busy = true
	var a: Dictionary = _toast_queue.pop_front()
	var p := PanelContainer.new()
	var sb: StyleBoxFlat = game._box(Color(0.09, 0.07, 0.06, 0.96), 14)
	sb.border_color = COL_NEON
	sb.set_border_width_all(2)
	sb.content_margin_left = 16
	sb.content_margin_right = 20
	sb.content_margin_top = 10
	sb.content_margin_bottom = 10
	p.add_theme_stylebox_override("panel", sb)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	h.add_child(game._label("★", 40, COL_NEON))
	var v := VBoxContainer.new()
	v.add_child(game._label("成就解锁", 18, Color("a8998a")))
	v.add_child(game._label(str(a.name), 26, Color("f6ede2")))
	h.add_child(v)
	p.add_child(h)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_layer.add_child(p)
	var screen_w := get_viewport_rect().size.x
	p.position = Vector2(screen_w + 10, 70)
	game._sfx("win")
	await get_tree().process_frame
	var x := screen_w - p.size.x - 16
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(p, "position:x", x, 0.35)
	tw.tween_interval(2.8)
	tw.tween_property(p, "modulate:a", 0.0, 0.4)
	tw.tween_callback(func() -> void:
		p.queue_free()
		_next_toast())

extends Node
## 录宣传视频用的自动演示：游戏自己玩一遍，配合 Godot 的 Movie Maker 录实机画面。
## 不进网页版（export_presets 排除了 dev/*）。
## 用法：Godot --path src --write-movie out.avi --fixed-fps 30 --resolution 720x1280 res://dev/demo.tscn
## 每个片段开始时打印 “CLIP 名字 秒数”，剪视频时按这个切。

var main: Node
var finger: Control
var _frames := 0


func _ready() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path("user://save.json"))  # 从新档开始
	main = load("res://main.tscn").instantiate()
	add_child(main)
	var layer := CanvasLayer.new()
	layer.layer = 100
	add_child(layer)
	finger = Control.new()
	finger.mouse_filter = Control.MOUSE_FILTER_IGNORE
	finger.draw.connect(_draw_finger)
	finger.modulate.a = 0.0
	layer.add_child(finger)
	_run.call_deferred()


func _process(_d: float) -> void:
	_frames += 1


func _now() -> float:
	return _frames / 30.0


func _clip(name: String) -> void:
	print("CLIP %s %.2f" % [name, _now()])


func _draw_finger() -> void:
	finger.draw_circle(Vector2.ZERO, 34, Color(1, 1, 1, 0.35))
	finger.draw_arc(Vector2.ZERO, 34, 0, TAU, 48, Color(1, 1, 1, 0.9), 4, true)


func _wait(s: float) -> void:
	await get_tree().create_timer(s).timeout


## 手指移过去点一下：真的发鼠标按下/抬起事件，跟手机上点一样
func _tap(pos: Vector2, hold := 0.08) -> void:
	if finger.modulate.a < 0.5:
		finger.position = pos + Vector2(60, 120)
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(finger, "modulate:a", 1.0, 0.15)
	tw.parallel().tween_property(finger, "position", pos, 0.35)
	await tw.finished
	_mouse(pos, true)
	var t2 := create_tween()
	t2.tween_property(finger, "scale", Vector2(0.75, 0.75), hold)
	await t2.finished
	_mouse(pos, false)
	create_tween().tween_property(finger, "scale", Vector2.ONE, 0.12)


func _hide_finger() -> void:
	create_tween().tween_property(finger, "modulate:a", 0.0, 0.25)


func _mouse(pos: Vector2, down: bool) -> void:
	var e := InputEventMouseButton.new()
	e.button_index = MOUSE_BUTTON_LEFT
	e.pressed = down
	var p: Vector2 = get_viewport().get_final_transform() * pos
	e.position = p
	e.global_position = p
	Input.parse_input_event(e)


func _tap_button(text: String) -> void:
	var b := _find_button(get_tree().root, text)
	if b == null:
		push_warning("找不到按钮：" + text)
		return
	await _tap(b.get_global_rect().get_center())


func _find_button(n: Node, text: String) -> Button:
	if n is CanvasItem and not n.is_visible_in_tree():
		return null
	if n is Button and n.text.begins_with(text) and not n.disabled:
		return n
	for c in n.get_children():
		var r := _find_button(c, text)
		if r:
			return r
	return null


func _run() -> void:
	await _wait(0.6)
	# 1. 大本营：员工从门口走进来，有人等你拍板
	_clip("home")
	main._set_employees([
		{"id": "a", "name": "修登录bug", "agent": "claude", "status": "waiting", "look": "claude_2", "project": "登录页"},
		{"id": "b", "name": "画商店图标", "agent": "codex", "status": "working", "look": "codex_1", "project": "美术"},
		{"id": "c", "name": "写单元测试", "agent": "deepseek", "status": "reported", "reported": true,
			"look": "deepseek_3", "project": "测试"},
		{"id": "d", "name": "整理文档", "agent": "claude", "status": "working", "look": "claude_5", "project": "文档"},
	])
	await _wait(4.5)
	# 点等你拍板的员工：立绘对话框
	_clip("dialog")
	var room: HomeRoom = main.room
	var a: Dictionary = room._actors["a"]
	await _tap(a.node.get_global_rect().get_center())
	await _wait(3.0)
	main._close_dialog()
	_hide_finger()
	await _wait(1.0)

	# 2. 开店：先把顾客换成会说谎的，好演示揭穿
	var tl: int = main.time_left
	for i in 40:
		if main.deal.lying:
			break
		main._next_customer()
		main.time_left = tl
	_clip("shop")
	var bar: Vector2 = room.to_screen(Vector2(0.5, 0.78))
	await _tap(bar)
	await _wait(3.0)  # 这些停顿按口播的句子长度调过
	# 检查：先看说谎的那一处
	_clip("clue")
	var lie_i := 0
	for i in main.deal.clues.size():
		if main.deal.clues[i].is_lie:
			lie_i = i
	var clue_btn: Button = main.clue_box.get_child(lie_i)
	await _tap(clue_btn.get_global_rect().get_center())
	await _wait(4.2)
	_clip("expose")
	await _tap(main.challenge_btn.get_global_rect().get_center())
	await _wait(2.4)
	_clip("haggle")
	await _tap_button("7 成")
	await _wait(0.9)
	await _tap(main.offer_btn.get_global_rect().get_center())
	await _wait(1.8)
	if main.deal_open:  # 顾客还价：直接按要价收
		await _tap(main.take_btn.get_global_rect().get_center())
		await _wait(1.0)
	_clip("result")
	await _wait(2.2)
	await _tap(main.result_btn.get_global_rect().get_center())
	_hide_finger()
	await _wait(2.5)

	# 3. 回大本营：员工带回包裹
	main._show_home()
	await _wait(1.2)
	_clip("gift")
	main._receive_gift("big", "claude")
	await _wait(1.6)
	await _tap(main.gift_action.get_global_rect().get_center())
	await _wait(2.6)
	await _tap(main.gift_action.get_global_rect().get_center())
	_hide_finger()
	await _wait(0.8)

	# 4. 抽造型
	main.cash = maxi(main.cash, 6000)
	main._refresh()
	_clip("gacha")
	await _tap_button("抽造型")
	await _wait(1.0)
	await _tap_button("抽 10 次")
	await _wait(3.5)
	main.meta_ui.close_panel()
	_hide_finger()
	await _wait(0.6)

	# 5. 升级、收藏室
	_clip("upgrades")
	await _tap_button("升级")
	await _wait(2.5)
	main.meta_ui.close_panel()
	await _wait(0.4)
	_clip("book")
	await _tap_button("收藏室")
	await _wait(2.5)
	_clip("end")
	await _wait(0.5)
	get_tree().quit()

class_name HomeRoom
extends Control
## 主页：探险队大本营。员工在房间里走动、喝咖啡、坐沙发；
## 有事等你拍板的员工会走到吧台前；点吧台开店，点员工弹出对话框（立绘 + 台词）。
## 位置都用背景图上的比例坐标（0~1），屏幕比例不同也能对上。

signal open_shop
signal staff_tapped(employee: Dictionary)

const WALK_SPEED := 120.0          ## 像素/秒（按 720 宽的画面）
const BOB_HEIGHT := 7.0
const BOB_FREQ := 11.0
const IDLE_WAIT := Vector2(1.2, 3.5)
const STAFF_HEIGHT := 230.0        ## 角色在房间最前排时的高度
const DEPTH_SCALE := Vector2(0.7, 1.08)  ## 房间最里面 → 最前面的缩放

# 背景图上的关键位置（比例坐标），按 lounge_bg.png 校准
const DOOR := Vector2(0.5, 0.285)
const FLOOR_RECT := Rect2(0.22, 0.37, 0.52, 0.24)     ## 可以随便走的地板（地毯一带）
const COFFEE_SPOTS := [Vector2(0.17, 0.40), Vector2(0.24, 0.42)]
const SOFA_SPOTS := [Vector2(0.84, 0.445), Vector2(0.93, 0.455), Vector2(0.76, 0.46)]
const BAR_FRONT_Y := 0.665                             ## 等你拍板的员工站在吧台前
const BAR_TOP := 0.70                                  ## 这条线以下是吧台，点击开店
const FLOOR_DEPTH := Vector2(0.29, 0.68)               ## 用来算远近缩放的纵向范围

var art_loader: Callable            ## func(name: String) -> Texture2D
var colors: Dictionary              ## agent -> Color
var tint_shader: Shader
var no_tint: Array = []

var _bg: TextureRect
var _actors := {}                   ## id -> {node, sprite, tag, idle_tag, alert, e, target, wait, t}
var _hint: Label
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.randomize()
	mouse_filter = Control.MOUSE_FILTER_STOP
	var ceiling := ColorRect.new()  # 背景图上方多出来的空间：深色天花板
	ceiling.color = Color("140d09")
	ceiling.set_anchors_preset(Control.PRESET_FULL_RECT)
	ceiling.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(ceiling)
	_bg = TextureRect.new()
	_bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_bg.stretch_mode = TextureRect.STRETCH_SCALE
	_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_bg.texture = art_loader.call("lounge_bg")
	if _bg.texture == null:
		_bg.texture = art_loader.call("shop_bg")
	add_child(_bg)
	_hint = Label.new()
	_hint.text = "点吧台开店"
	_hint.add_theme_font_size_override("font_size", 24)
	_hint.add_theme_color_override("font_color", Color("ffb347"))
	_hint.add_theme_constant_override("outline_size", 8)
	_hint.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_hint)
	var tw := create_tween().set_loops()
	tw.tween_property(_hint, "modulate:a", 0.35, 0.9)
	tw.tween_property(_hint, "modulate:a", 1.0, 0.9)
	resized.connect(_on_resized)


## 背景图在屏幕上的位置：完整显示、贴底、左右居中（手机上正好铺满宽度，上方留给招牌）
func bg_rect() -> Rect2:
	var tex := _bg.texture
	if tex == null:
		return Rect2(Vector2.ZERO, size)
	var ts := Vector2(tex.get_width(), tex.get_height())
	var s := minf(size.x / ts.x, size.y / ts.y)   # 整张图完整放进来，不裁切
	var draw := ts * s
	return Rect2(Vector2((size.x - draw.x) / 2.0, size.y - draw.y), draw)


## 背景图比例坐标 → 屏幕坐标
func to_screen(p: Vector2) -> Vector2:
	var r := bg_rect()
	return r.position + p * r.size


func to_norm(screen: Vector2) -> Vector2:
	var r := bg_rect()
	return (screen - r.position) / r.size


func _on_resized() -> void:
	var r := bg_rect()
	_bg.position = r.position
	_bg.size = r.size
	var p := to_screen(Vector2(0.5, BAR_TOP + 0.075))
	_hint.position = Vector2(0, p.y)
	_hint.size = Vector2(size.x, 40)
	for id in _actors:
		var a: Dictionary = _actors[id]
		a.node.position = to_screen(a.norm)


## 更新员工名单：新来的从门口走进来，离开的消失，状态变了就换去处
func set_employees(list: Array, animate_entry: bool) -> void:
	var seen := {}
	var delay := 0.0
	for e in list:
		seen[e.id] = true
		if _actors.has(e.id):
			var a: Dictionary = _actors[e.id]
			var old_status: String = a.e.get("status", "")
			a.e = e
			_refresh_tags(a)
			if old_status != str(e.get("status", "")):
				_choose_target(a)
		else:
			_spawn(e, delay if animate_entry else -1.0)
			delay += 0.6
	for id in _actors.keys():
		if not seen.has(id):
			_actors[id].node.queue_free()
			_actors.erase(id)


## 重新播放所有人从门口走进来（每次回到主页时）
func replay_entry() -> void:
	var delay := 0.2
	for id in _actors:
		var a: Dictionary = _actors[id]
		a.norm = DOOR
		a.wait = delay
		a.node.modulate.a = 0.0
		a.entering = true
		delay += 0.55
		_choose_target(a)


func _spawn(e: Dictionary, delay: float) -> void:
	var node := Control.new()
	node.mouse_filter = Control.MOUSE_FILTER_STOP
	node.size = Vector2(STAFF_HEIGHT * 0.66, STAFF_HEIGHT)
	node.pivot_offset = Vector2(STAFF_HEIGHT * 0.33, STAFF_HEIGHT)
	var sprite := TextureRect.new()
	sprite.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	sprite.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	sprite.size = node.size
	sprite.mouse_filter = Control.MOUSE_FILTER_IGNORE
	node.add_child(sprite)
	# 头顶的小白名牌（只写名字），空闲时旁边多一个“空闲”
	var tag := PanelContainer.new()
	tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tag_box := HBoxContainer.new()
	tag_box.add_theme_constant_override("separation", 6)
	var dot := Panel.new()
	dot.custom_minimum_size = Vector2(10, 10)
	dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	tag_box.add_child(dot)
	var name_lbl := Label.new()
	name_lbl.add_theme_font_size_override("font_size", 22)
	name_lbl.add_theme_color_override("font_color", Color("2a1d14"))
	tag_box.add_child(name_lbl)
	var idle_lbl := Label.new()
	idle_lbl.text = "空闲"
	idle_lbl.add_theme_font_size_override("font_size", 16)
	idle_lbl.add_theme_color_override("font_color", Color("2f9e63"))
	tag_box.add_child(idle_lbl)
	tag.add_child(tag_box)
	node.add_child(tag)
	# 等你拍板时头上跳的感叹号
	var alert := Label.new()
	alert.text = "!"
	alert.add_theme_font_size_override("font_size", 44)
	alert.add_theme_color_override("font_color", Color("ff5d5d"))
	alert.add_theme_constant_override("outline_size", 10)
	alert.add_theme_color_override("font_outline_color", Color.WHITE)
	alert.mouse_filter = Control.MOUSE_FILTER_IGNORE
	node.add_child(alert)
	add_child(node)
	var a := {"node": node, "sprite": sprite, "tag": tag, "dot": dot, "name": name_lbl, "idle": idle_lbl,
		"alert": alert, "e": e, "norm": DOOR, "target": DOOR, "wait": maxf(delay, 0.0), "t": _rng.randf() * 10.0,
		"entering": delay >= 0.0, "spot": -1}
	_actors[e.id] = a
	node.gui_input.connect(_on_actor_input.bind(e.id))
	if delay < 0.0:
		a.norm = _random_floor()
	else:
		node.modulate.a = 0.0
	_refresh_tags(a)
	_choose_target(a)
	node.position = to_screen(a.norm)


func _refresh_tags(a: Dictionary) -> void:
	var e: Dictionary = a.e
	var color: Color = colors.get(e.agent, Color("ffb347"))
	var look = e.get("look", "staff_1")
	var tex: Texture2D = art_loader.call(str(look))
	if tex == null:
		tex = art_loader.call("staff_%d" % (absi(hash(str(e.id))) % 8 + 1))
	a.sprite.texture = tex
	if tint_shader and not no_tint.has(str(look)):
		var mat := ShaderMaterial.new()
		mat.shader = tint_shader
		mat.set_shader_parameter("tint_color", color)
		a.sprite.material = mat
	else:
		a.sprite.material = null
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(1, 0.98, 0.94, 0.95)
	sb.set_corner_radius_all(10)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 3
	sb.content_margin_bottom = 3
	sb.shadow_color = Color(0, 0, 0, 0.35)
	sb.shadow_size = 4
	a.tag.add_theme_stylebox_override("panel", sb)
	var dsb := StyleBoxFlat.new()
	dsb.bg_color = color
	dsb.set_corner_radius_all(5)
	a.dot.add_theme_stylebox_override("panel", dsb)
	a.name.text = str(e.get("name", "员工"))
	var status := str(e.get("status", "working"))
	a.idle.visible = status == "resting"
	a.alert.visible = status == "waiting"


## 根据状态决定去哪：忙碌的到处走，空闲的去沙发/咖啡机，等你拍板的来吧台前
func _choose_target(a: Dictionary) -> void:
	match str(a.e.get("status", "working")):
		"waiting":
			a.target = Vector2(0.38 + _rng.randf() * 0.24, BAR_FRONT_Y)
		"resting":
			var spots: Array = SOFA_SPOTS + COFFEE_SPOTS
			a.target = spots[_free_spot(spots, a)]
		_:
			a.target = COFFEE_SPOTS[_rng.randi_range(0, 1)] if _rng.randf() < 0.2 else _random_floor()


func _free_spot(spots: Array, me: Dictionary) -> int:
	var taken := {}
	for id in _actors:
		var o: Dictionary = _actors[id]
		if o != me and o.spot >= 0 and str(o.e.get("status", "")) == "resting":
			taken[o.spot] = true
	for i in spots.size():
		if not taken.has(i):
			me.spot = i
			return i
	me.spot = _rng.randi_range(0, spots.size() - 1)
	return me.spot


func _random_floor() -> Vector2:
	return FLOOR_RECT.position + Vector2(_rng.randf(), _rng.randf()) * FLOOR_RECT.size


func _process(delta: float) -> void:
	if not visible:
		return
	if not _bg.size.is_equal_approx(bg_rect().size):
		_on_resized()  # 第一次布局或屏幕旋转后，背景还没摆好
	var ids := _actors.keys()
	for id in ids:
		var a: Dictionary = _actors[id]
		a.t += delta
		var node: Control = a.node
		if a.wait > 0.0:
			a.wait -= delta
			if a.entering and a.wait <= 0.0:
				create_tween().tween_property(node, "modulate:a", 1.0, 0.25)
			continue
		var here := to_screen(a.norm)
		var there := to_screen(a.target)
		var dist := here.distance_to(there)
		var bob := 0.0
		if dist > 3.0:
			var step := minf(dist, WALK_SPEED * (_bg.size.x / 720.0) * delta)
			here = here.move_toward(there, step)
			a.norm = to_norm(here)
			bob = -absf(sin(a.t * BOB_FREQ)) * BOB_HEIGHT
			a.sprite.flip_h = there.x < here.x
			a.sprite.rotation = sin(a.t * BOB_FREQ) * 0.04
		else:
			a.sprite.rotation = 0.0
			a.entering = false
			if str(a.e.get("status", "")) == "working":
				a.wait = _rng.randf_range(IDLE_WAIT.x, IDLE_WAIT.y)
				_choose_target(a)
		# 远小近大
		var depth := clampf(inverse_lerp(FLOOR_DEPTH.x, FLOOR_DEPTH.y, a.norm.y), 0.0, 1.0)
		var room_w := _bg.size.x / 720.0  # 按房间图实际显示的宽度缩放
		var sc := lerpf(DEPTH_SCALE.x, DEPTH_SCALE.y, depth) * room_w
		node.scale = Vector2(sc, sc)
		node.position = here - Vector2(node.size.x / 2.0, node.size.y) + Vector2(0, bob)
		a.sprite.position = Vector2.ZERO
		# 名牌不跟着远近缩得太小，保证手机上看得清
		var keep := clampf(room_w / sc, 1.0, 1.5)
		a.tag.scale = Vector2(keep, keep)
		a.tag.position = Vector2((node.size.x - a.tag.size.x * keep) / 2.0, -a.tag.size.y * keep - 6)
		a.alert.position = Vector2(node.size.x / 2.0 - 8, -a.tag.size.y - 62 + sin(a.t * 6.0) * 6.0)
		a.y = here.y


	_sort_by_depth()


## 靠前（y 大）的员工画在上面。用子节点顺序而不是 z_index，免得盖住主页上的招牌和按钮
func _sort_by_depth() -> void:
	var list := _actors.values()
	list.sort_custom(func(a, b): return a.get("y", 0.0) < b.get("y", 0.0))
	var base := _hint.get_index()
	for i in list.size():
		move_child(list[i].node, base + i)


func _on_actor_input(event: InputEvent, id: String) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		accept_event()
		staff_tapped.emit(_actors[id].e)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if to_norm(event.position).y >= BAR_TOP:
			open_shop.emit()

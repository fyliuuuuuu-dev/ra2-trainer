"""红警2 (Red Alert 2) 内存地址表。

坐标约定：
  - va     : 模块内虚拟地址（imagebase = 0x400000，游戏无 ASLR）
  - off    : 关闭状态下的原始字节
  - on     : 开启状态下写入的字节
已验证版本：RA2 1.006 (game.exe, 时间戳 2001-06-06)
"""

IMAGE_BASE = 0x400000

# 用于识别游戏版本的特征码（原始未修改状态）
VERSION_SIGS = {
    "money_no_decrease": (0x4E53A9, "2bc7"),
    "reveal_map":        (0x4F2FF8, "744a"),
    "build_anywhere_1":  (0x49BC1C, "0f84c4010000"),
    "build_anywhere_2":  (0x49BC2A, "0f84b6010000"),
    "radar_1":           (0x4F2F1A, "7449"),
    "radar_2":           (0x632F39, "755d"),
}

PROFILES = [
    {
        "id": "ra2",
        "name": "命令与征服：红色警戒2",
        "exe": "game.exe",
        "launcher": "ra2.exe",
        "base": IMAGE_BASE,
        "desc": "原版 1.006",
    },
]

# 代码补丁型功能：type = "patch"
# 每个补丁 = (va, 原始字节, 开启字节)
PATCHES = {
    "money_no_decrease": {
        "name": "金钱不减",
        "section": "玩家",
        "sites": [(0x4E53A9, "2bc7", "eb58")],
        "note": "花费不再扣除资金",
    },
    "build_anywhere": {
        "name": "无视建造距离",
        "section": "玩家",
        "sites": [
            (0x49BC1C, "0f84c4010000", "909090909090"),
            (0x49BC2A, "0f84b6010000", "909090909090"),
        ],
        "note": "允许在基地范围外建造建筑",
    },
    "reveal_map": {
        "name": "显示全图",
        "section": "视觉",
        "sites": [(0x4F2FF8, "744a", "9090")],
        "note": "揭开整张地图（只要拥有建筑）",
    },
    "radar": {
        "name": "雷达始终开启",
        "section": "视觉",
        "sites": [
            (0x4F2F1A, "7449", "9090"),
            (0x632F39, "755d", "9090"),
        ],
        "note": "无条件点亮小地图雷达",
    },

}

# ---------------------------------------------------------------- 运行时定位结果
# 以下地址由 tools/houses.py 在 RA2 1.006 实机验证（2026-09-27）
PLAYER_PTR = 0xA35DB4      # HouseClass::Player  —— 指向玩家势力的全局指针
HOUSE_ARRAY = 0xA3229C     # HouseClass::Array   —— DynamicVectorClass（Items@+0, Count@+0xC）
HOUSE_ARRAY_ALT = 0xAC0C34 # 另一个同内容向量（仅 5 处引用，非主表）
FRAME = 0xA40D2C           # 游戏帧计数器
SELECTED_DATA = 0xA40C64   # 当前选中对象 DynamicVectorClass Items
SELECTED_COUNT = 0xA40C70  # 当前选中对象数量
TECHNO_ARRAY = 0xA40C24    # TechnoClass::Array Items（DynamicVectorClass 对象在 0xA40C20）
TECHNO_COUNT = 0xA40C30    # TechnoClass::Array Count；构造函数 0x6C1180 附近加入，析构 0x6C216B 移除

# 对象 vtable（最派生类，见 objscan.OBJ_VT）
HOUSE_VT = 0x7A2DE0
UNIT_VT = 0x7ADDF8
INFANTRY_VT = 0x7A3540
BUILDING_VT = 0x79CBBC
AIRCRAFT_VT = 0x79B12C
SUPER_VT = 0x7AC210

# HouseClass 关键字段偏移（实测）
HOUSE_FIELD = {
    "Type": 0x34,                # HouseTypeClass*
    "StartingCredits": 0x124,    # 初始资金
    "Credits": 0x24C,            # 当前资金（屏幕显示值）
    "PowerOutput": 0x52D0,       # 电力产出
    "PowerDrain": 0x52D4,        # 电力负载
    "Buildings_Items": 0x6C,     # DynamicVectorClass<BuildingClass*> Items
    "Buildings_Count": 0x78,     # Count = Items + 0xC
}

# 相关代码（仅供分析参考，不参与补丁）
CODE = {
    "Power_Fraction": 0x4E8330,   # 返回 double：Output/Drain，充足时返回 1.0
    "Recalculate_Power": 0x4F2CC0,  # 清零后遍历建筑累加 Output/Drain
    "Adjust_Power_Output": 0x4EC6E0,
    "Adjust_Power_Drain": 0x4EC850,
    "Set_Credits": 0x4E8300,      # __thiscall SetCredits(this, a1, a2, credits)
}

# ---------------------------------------------------------------- 技术类（单位/建筑）字段
# 由 tools/objects.py 实机验证（RA2 1.006）
TECHNO_FIELD = {
    "Owner": 0x1B4,              # HouseClass*（271/274 命中）
    "Veterancy": 0x11C,          # float 老兵等级：0=新兵 1=老兵 2=精英(三星)
    "Health": 0x6C,              # 血量（与 EstimatedHealth 成对）
    "EstimatedHealth": 0x70,
    "ArmorMultiplier": 0x120,    # double，默认 1.0
    "FirepowerMultiplier": 0x128,# double，默认 1.0
}

# 各类别 Type(TechnoTypeClass*) 字段偏移（实测）
CLASS_TYPE_OFF = {
    0x7A3540: 0x5A8,   # InfantryClass
    0x7ADDF8: 0x5AC,   # UnitClass
    0x79B12C: 0x5AC,   # AircraftClass
    0x79CBBC: 0x418,   # BuildingClass
}

# 一次性「执行型」功能
ACTION_FEATURES = {
    "u_vet3": {
        "name": "我军升三星",
        "section": "单位操作",
        "op": "set_unit_field",
        "fields": [(TECHNO_FIELD["Veterancy"], "f32")],
        "value": 2.0,
        "desc": "把己方全部单位的老兵等级设为精英（三星）",
    },
}

# 需要「持续生效」的功能（开关打开后由主循环周期性重写，新造的单位也会生效）
# 我军升三星、自动修理建筑已改为 techno_ai 钩子，不在此轮询
# kinds: 只对这几类对象生效（None = 全部）
LOOP_ACTIONS = {
    "sw_no_wait": {"name": "超武无等待", "op": "charge_supers"},
    "u_regen": {"name": "单位回复", "op": "heal", "selected": True,
                "kinds": [0x7ADDF8, 0x7A3540, 0x79B12C]},
}

# 作用于「玩家全部单位」的数值功能
# fields = [(偏移, 类型)]，类型见 mem.Process.read_value/write_value
UNIT_FEATURES = {
    "u_hp": {
        "name": "单位血量",
        "section": "单位编辑",
        "fields": [(TECHNO_FIELD["Health"], "i32"),
                   (TECHNO_FIELD["EstimatedHealth"], "i32")],
        "desc": "把玩家所有单位的血量改为该值",
    },
    "u_armor": {
        "name": "单位装甲倍率",
        "section": "单位编辑",
        "fields": [(TECHNO_FIELD["ArmorMultiplier"], "f64")],
        "desc": "1.0 = 正常；越大越抗打",
    },
    "u_firepower": {
        "name": "单位火力倍率",
        "section": "单位编辑",
        "fields": [(TECHNO_FIELD["FirepowerMultiplier"], "f64")],
        "desc": "1.0 = 正常；越大伤害越高",
    },
}

# 需要指针链的数值功能
# chain = [全局指针地址, 最终字段偏移]，解析方式：*( *(chain[0]) + chain[1] )
POINTER_FEATURES = {
    "credits": {
        "name": "金钱数量",
        "section": "玩家",
        "desc": "设置玩家当前资金",
        "chain": [PLAYER_PTR, HOUSE_FIELD["Credits"]],
    },
}

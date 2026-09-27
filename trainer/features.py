"""功能清单（参照 BnB修改器v5.2.1 的分区与条目）。

status:
  ok   - 地址已验证可用，界面正常可用
  todo - 条目已登记，地址待逆向定位（界面置灰）
kind:
  patch  - 代码补丁（开启写 on 字节，关闭还原 off 字节）
  value  - 读/写数值（需指针链）
  action - 一次性执行
  debug  - 调试工具（扫描/指针查找等）
"""

SECTIONS = ["玩家", "战役", "经济", "战斗", "视觉", "超武", "单位编辑", "单位操作", "载具&建筑", "调试"]

FEATURES = [
    # ---------------- 玩家 ----------------
    dict(id="credits", name="金钱数量", section="玩家", kind="value", status="ok",
         info="设置玩家当前资金（0xA35DB4 -> +0x24C，实测可用）"),
    dict(id="money_no_decrease", name="金钱不减", section="玩家", kind="patch", status="ok",
         info="花费不再扣除资金（补丁 0x4E53A9）"),
    dict(id="unlimited_queue", name="扩展建造队列", section="玩家", kind="patch", status="ok",
         info="己方生产队列上限扩展至999；仍遵守单位数量限制"),
    dict(id="instant_build", name="瞬间完成建造", section="玩家", kind="patch", status="ok",
         info="己方生产立即进入最后付款步骤；资金不足会等待，手动暂停仍有效"),
    dict(id="build_anywhere", name="无视建造距离", section="玩家", kind="patch", status="ok",
         info="可在基地范围外建造建筑（补丁 0x49BC1C / 0x49BC2A）"),
    dict(id="no_obstacle", name="无视任何阻碍", section="玩家", kind="patch", status="todo",
         info="放置不受阻挡限制"),
    dict(id="fast_build", name="快速建造", section="玩家", kind="patch", status="ok",
         info="己方约10倍建造速度，最快每帧推进一格；瞬间建造开启时优先生效"),
    dict(id="infinite_power", name="无限电力", section="玩家", kind="patch", status="ok",
         info="仅己方供电充足；同步更新建筑与小地图，关闭后恢复实际电力"),
    dict(id="invincible", name="无敌模式", section="玩家", kind="patch", status="ok",
         info="拦截己方单位和建筑的普通伤害；出售、脚本强制销毁与控制权变化不受保护"),
    dict(id="auto_repair", name="自动修理建筑", section="玩家", kind="patch", status="ok",
         info="建筑持续自动回血"),
    dict(id="repair_amount", name="设置修理恢复量", section="玩家", kind="value", status="ok",
         info="自动修理建筑每次恢复的血量（0=满血，1～1000000=指定血量；每15个游戏帧一次，常速约1秒）"),
    dict(id="sell_all", name="可以出售一切", section="玩家", kind="patch", status="todo",
         info="可出售任意建筑/单位"),
    dict(id="anti_stealth", name="反隐身伪装", section="玩家", kind="patch", status="ok",
         info="仅己方识破敌人的隐身与伪装；关闭后恢复原有侦测"),
    dict(id="crack_gens", name="瘫痪裂缝产生器", section="玩家", kind="patch", status="todo",
         info="让对手裂缝产生器失效"),
    dict(id="psy_scan", name="心灵探测", section="玩家", kind="patch", status="ok",
         info="全图显示非盟军载具/步兵/飞机的移动与攻击路线，效果同心灵探测器覆盖全图"),
    dict(id="tech_all", name="科技全开", section="玩家", kind="patch", status="ok",
         info="己方开放正常跨阵营科技及建造前提；仍需真实类别工厂，不解锁硬禁用类型；机场按阵营保留一种"),
    dict(id="unlock_build", name="解除建造限制", section="玩家", kind="patch", status="ok",
         info="仅己方无视建造前提与数量上限；不取消硬禁用与工厂需求"),
    dict(id="radar", name="雷达+间谍卫星", section="玩家", kind="patch", status="ok",
         info="无条件点亮小地图（补丁 0x4F2F1A / 0x632F39）"),
    dict(id="clear_shroud", name="透明迷雾", section="玩家", kind="patch", status="todo",
         info="迷雾半透明显示"),
    dict(id="turn_speed", name="单位转向速度", section="玩家", kind="value", status="ok",
         info="设置选中单位所属类型的转向速度（1～127）；同类型共享"),

    # ---------------- 视觉 ----------------
    dict(id="reveal_map", name="显示全图", section="视觉", kind="patch", status="ok",
         info="揭开整张地图（补丁 0x4F2FF8）"),

    # ---------------- 超武 ----------------
    dict(id="sw_no_wait", name="超武无等待", section="超武", kind="patch", status="ok",
         info="己方已获得且未暂停的超级武器及空降支援立即充能"),
    dict(id="sw_fire", name="发射超武", section="超武", kind="action", status="todo",
         info="直接发射选中超武"),

    # ---------------- 单位编辑 ----------------
    dict(id="u_hp", name="单位血量", section="单位编辑", kind="value", status="ok",
         info="写 TechnoClass+0x6C/0x70（作用于己方全部单位）"),
    dict(id="u_speed", name="单位移速倍率", section="单位编辑", kind="value", status="ok",
         info="修改选中单位所属类型的基础移速倍率（0.1～10）；影响所有势力的同类型单位"),
    dict(id="u_firepower", name="单位火力倍率", section="单位编辑", kind="value", status="ok",
         info="写 TechnoClass+0x128 double（作用于己方全部单位）"),
    dict(id="u_armor", name="单位装甲倍率", section="单位编辑", kind="value", status="ok",
         info="写 TechnoClass+0x120 double（作用于己方全部单位）"),
    dict(id="u_sight", name="单位视野", section="单位编辑", kind="value", status="ok",
         info="修改选中单位所属类型的视野（0～30）；影响同类型单位，移动后刷新视野"),
    dict(id="u_unselectable", name="单位不可选中", section="单位编辑", kind="value", status="ok",
         info="1=不可选中，0=可选中；同类型共享，使用“还原类型修改”可恢复"),
    dict(id="u_invisible", name="单位可隐形", section="单位编辑", kind="value", status="ok",
         info="1=允许隐形，0=禁用；同类型共享，是否立即隐形取决于单位状态"),
    dict(id="u_detect", name="单位探测隐形", section="单位编辑", kind="value", status="ok",
         info="1=启用隐形探测，0=关闭；同类型共享，具体范围由原游戏规则决定"),
    dict(id="u_rad_immune", name="单位免疫辐射", section="单位编辑", kind="value", status="ok",
         info="1=免疫辐射，0=不免疫；所有势力同类型共享"),
    dict(id="u_cost", name="单位成本", section="单位编辑", kind="value", status="ok",
         info="修改选中单位所属类型的价格；所有势力同类型共享"),
    dict(id="u_sell", name="单位出售价值", section="单位编辑", kind="value", status="todo",
         info="设置选中单位的出售价值"),

    # ---------------- 单位操作 ----------------
    dict(id="u_regen", name="单位回复", section="单位操作", kind="patch", status="ok",
         info="选中的己方载具/步兵/飞机持续恢复到满血"),
    dict(id="u_seize", name="占有选中单位", section="单位操作", kind="action", status="ok",
         info="把选中单位变为己方"),
    dict(id="u_transfer", name="转移单位控制权", section="单位操作", kind="action", status="ok",
         info="把选中单位转移给指定玩家"),
    dict(id="u_iron_curtain", name="给单位铁幕", section="单位操作", kind="action", status="todo",
         info="对选中单位施加铁幕"),
    dict(id="u_iron_cancel", name="取消铁幕", section="单位操作", kind="action", status="todo",
         info="取消选中单位的铁幕"),
    dict(id="u_vet3", name="我军升三星", section="单位操作", kind="patch", status="ok",
         info="开关打开后持续把己方载具/步兵/飞机升到三星，新造单位也生效（不含建筑）"),
    dict(id="u_clone", name="复制选中单位", section="单位操作", kind="action", status="ok",
         info="把选中的己方地面载具/步兵一次性复制到游戏鼠标附近（最多500个）；步兵可多人同格，能否放下由游戏规则决定，放不下的会清理"),
    dict(id="u_one_hit", name="一击必杀", section="单位操作", kind="patch", status="todo",
         info="攻击一击秒杀"),
    dict(id="u_all_target", name="全目标攻击（含对空）", section="单位操作", kind="patch", status="ok",
         info="己方已有武器可瞄准并命中空中/地面目标；仍受射程、弹道与装填限制"),
    dict(id="chrono_quick_land", name="时空兵快速落地", section="单位操作", kind="patch", status="ok",
         info="仅己方时空移动步兵后续传送的落地等待缩至1游戏帧；不改变武器抹除时间与落点判定"),
    dict(id="water_walk", name="陆地单位水面行走", section="单位操作", kind="patch", status="ok",
         info="己方原本不能下水的普通步兵和地面战车可经过海滩进入水面；关闭后水上单位仍可返岸，原生两栖单位不变"),
    dict(id="u_aggressive", name="侵略模式", section="单位操作", kind="patch", status="todo",
         info="单位主动进攻"),
    dict(id="u_fly", name="所选单位飞天", section="单位操作", kind="action", status="todo",
         info="选中单位升空"),
    dict(id="u_land", name="所选单位降落", section="单位操作", kind="action", status="todo",
         info="选中单位降落"),
    dict(id="u_teleport_enemies", name="传送全部敌人单位", section="单位操作", kind="action", status="todo",
         info="把敌方单位传送到指定位置"),

    # ---------------- 载具&建筑 ----------------
    dict(id="tank_auto_repair", name="坦克自动维修", section="载具&建筑", kind="patch", status="ok",
         info="己方可维修的地面战车按原版维修厂速度修理；舰船、飞机、步兵和建筑不受影响"),
    dict(id="airport_slots", name="空军指挥部机位倍率", section="载具&建筑", kind="value", status="ok",
         info="设置己方空军指挥部机位为原版4个的1～16倍；现有飞机保留，多个飞机可共用原停机坪位置"),
    dict(id="v_unload_all", name="释放所有载员", section="载具&建筑", kind="action", status="todo",
         info="载具卸下全部乘员"),
    dict(id="v_infantry_board", name="步兵自动上车", section="载具&建筑", kind="patch", status="todo",
         info="步兵自动进入空载具"),
    dict(id="v_auto_enter", name="选中步兵进驻建筑", section="载具&建筑", kind="action", status="ok",
         info="执行一次：使当时选中的己方驻防步兵进入30格内（约一屏）有空位的己方或平民建筑；是否可进由游戏原生规则判断"),

    dict(id="restore_types", name="还原类型修改", section="单位编辑", kind="action", status="ok",
         info="还原本次修改器对单位类型的修改；正常关闭修改器时也会还原"),

    # ---------------- 战役 ----------------
    dict(id="mission_timer_freeze", name="冻结任务倒计时", section="战役", kind="patch", status="ok",
         info="任务计时器保持当前剩余时间，不会到时触发失败；任务中途重设计时器会以新时间继续冻结"),
    dict(id="mission_win", name="任务直接胜利", section="战役", kind="action", status="ok",
         info="立即以胜利结束当前战局（与地图触发的胜利相同），战役会进入下一关"),
    dict(id="campaign_all", name="盟军战役起始关", section="战役", kind="value", status="ok",
         info="在游戏主菜单设置1～12，再点“盟军战役”即从该关开始；关闭修改器后恢复从第1关开始"),
    dict(id="campaign_sov", name="苏军战役起始关", section="战役", kind="value", status="ok",
         info="在游戏主菜单设置1～12，再点“苏军战役”即从该关开始；关闭修改器后恢复从第1关开始"),

    # ---------------- 经济 ----------------
    dict(id="ore_income", name="采矿收入倍率", section="经济", kind="value", status="ok",
         info="己方矿车卸矿所得资金乘以该倍率（0.1～100，1为原版）；含净化工厂加成"),
    dict(id="ore_infinite", name="矿石无限", section="经济", kind="patch", status="ok",
         info="己方矿车采矿不减少矿区的矿石；敌方采矿照常消耗"),
    dict(id="repair_free", name="修理免费", section="经济", kind="patch", status="ok",
         info="己方建筑修理和维修厂修理载具不花钱"),
    dict(id="sell_full", name="出售全额退款", section="经济", kind="patch", status="ok",
         info="己方出售建筑、回收单位退还全部造价（原版为一半）"),

    # ---------------- 战斗 ----------------
    dict(id="rof_mult", name="己方射速倍率", section="战斗", kind="value", status="ok",
         info="己方所有单位和防御建筑的开火间隔缩短为 1/倍率（1～10，1为原版）"),
    dict(id="range_mult", name="己方射程倍率", section="战斗", kind="value", status="ok",
         info="己方武器射程和索敌距离乘以该倍率（0.5～5，1为原版）；超出视野的目标仍需先被发现"),

    dict(id="anti_mind_control", name="反尤里控制", section="战斗", kind="patch", status="ok",
         info="己方单位和建筑不会被尤里心灵控制，尤里也不会把它们当作控制目标；开启前已被控制的单位不会自动放回"),

    # ---------------- 调试 ----------------
    dict(id="dbg_sig", name="校验游戏版本与补丁", section="调试", kind="debug", status="ok",
         info="读取特征码确认是否为 RA2 1.006，以及各补丁当前状态"),
    dict(id="dbg_scan", name="按数值扫描内存", section="调试", kind="debug", status="ok",
         info="输入整数，列出所有存放该值的地址（用于定位资金等）"),
    dict(id="dbg_ptr", name="按地址查找指针", section="调试", kind="debug", status="ok",
         info="输入地址，列出指向它的全局变量（用于定位 Player 指针）"),
]

DEBUG_ACTIONS = {"dbg_sig", "dbg_scan", "dbg_ptr"}

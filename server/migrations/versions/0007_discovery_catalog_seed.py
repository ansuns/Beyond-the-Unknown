from alembic import op

revision = "0007_discovery_catalog_seed"
down_revision = "0006_mech_catalog_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO discovery_catalog
            (discovery_id, discovery_type, level_id, location, related_rule, display_name)
        VALUES
            ('DIS_RULE_ECHO', 'DIS_RULE_EFFECT', NULL,
             '{"scope":"WORLD","rule_id":"RULE_ECHO"}'::jsonb,
             'RULE_ECHO', '回声法则'),
            ('DIS_RULE_GAZE', 'DIS_RULE_EFFECT', NULL,
             '{"scope":"WORLD","rule_id":"RULE_GAZE"}'::jsonb,
             'RULE_GAZE', '注视法则'),
            ('DIS_RULE_REVERSE', 'DIS_RULE_EFFECT', NULL,
             '{"scope":"WORLD","rule_id":"RULE_REVERSE"}'::jsonb,
             'RULE_REVERSE', '逆流法则'),
            ('DIS_COMBO_001', 'DIS_COMBO', 'LV-ROOM-02',
             '{"level_id":"LV-ROOM-02","combo_id":"COMBO-001"}'::jsonb,
             NULL, '回声与注视的桥梁组合'),
            ('DIS_COMBO_002', 'DIS_COMBO', 'LV-ROOM-03',
             '{"level_id":"LV-ROOM-03","combo_id":"COMBO-002"}'::jsonb,
             NULL, '回声与逆流的能量组合'),
            ('DIS_COMBO_003', 'DIS_COMBO', 'LV-ROOM-04',
             '{"level_id":"LV-ROOM-04","combo_id":"COMBO-003"}'::jsonb,
             NULL, '注视与逆流的平台组合'),
            ('DIS_HIDDEN_OBJ_LV_ROOM_01_HIDDEN_01', 'DIS_HIDDEN_OBJ', 'LV-ROOM-01',
             '{"level_id":"LV-ROOM-01","mechanism_id":"MECH-ROOM01-HIDDEN-01"}'::jsonb,
             'RULE_ECHO', '遗忘森林中的隐藏物体'),
            ('DIS_HIDDEN_ROUTE_CLUE_01', 'DIS_HIDDEN_AREA', 'LV-ROOM-05',
             '{"level_id":"LV-ROOM-05","mechanism_id":"M05-HIDDEN-01"}'::jsonb,
             'RULE_ECHO', '隐藏路线线索'),
            ('DIS_ENDING_HIDDEN_01', 'DIS_ENDING', 'LV-HIDDEN-01',
             '{"level_id":"LV-HIDDEN-01","ending_id":"ENDING-01"}'::jsonb,
             NULL, '无界之外')
        ON CONFLICT (discovery_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO collection_catalog
            (collection_id, codex_category, source_discovery_id,
             display_name, description, sort_order)
        VALUES
            ('COLL_RULE_ECHO', 'CAT_RULE', 'DIS_RULE_ECHO',
             '回声法则', '记录首次成功触发回声法则的发现。', 10),
            ('COLL_RULE_GAZE', 'CAT_RULE', 'DIS_RULE_GAZE',
             '注视法则', '记录首次成功触发注视法则的发现。', 20),
            ('COLL_RULE_REVERSE', 'CAT_RULE', 'DIS_RULE_REVERSE',
             '逆流法则', '记录首次成功触发逆流法则的发现。', 30),
            ('COLL_COMBO_001', 'CAT_RELIC', 'DIS_COMBO_001',
             '桥梁组合', '记录首次发现 COMBO-001。', 110),
            ('COLL_COMBO_002', 'CAT_RELIC', 'DIS_COMBO_002',
             '能量组合', '记录首次发现 COMBO-002。', 120),
            ('COLL_COMBO_003', 'CAT_RELIC', 'DIS_COMBO_003',
             '平台组合', '记录首次发现 COMBO-003。', 130),
            ('COLL_HIDDEN_OBJ_01', 'CAT_RELIC', 'DIS_HIDDEN_OBJ_LV_ROOM_01_HIDDEN_01',
             '遗忘森林的隐秘造物', '记录首次显现遗忘森林中的隐藏物体。', 210),
            ('COLL_HIDDEN_ROUTE_01', 'CAT_AREA', 'DIS_HIDDEN_ROUTE_CLUE_01',
             '失落路线线索', '记录首次发现隐藏路线线索。', 220),
            ('COLL_HIDDEN_ENDING_01', 'CAT_ENDING', 'DIS_ENDING_HIDDEN_01',
             '隐藏结局', '记录首次达成首期隐藏结局。', 310)
        ON CONFLICT (collection_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO rewards
            (reward_id, reward_type, reward_name, condition_ref,
             grant_mode, payload, is_paid, is_enabled)
        VALUES
            ('REWARD_WORLD_FIRST_TITLE', 'RT_TITLE', '世界先行者',
             'WORLD_FIRST_DISCOVERY', 'AUTO',
             '{"title_id":"TITLE_WORLD_PIONEER","honor_only":true}'::jsonb,
             false, true)
        ON CONFLICT (reward_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Preserve player discovery/archive/collection records during data-only downgrade.
    pass

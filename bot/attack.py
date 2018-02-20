from math import pi
from sc2.constants import AbilityId, UnitTypeId

class Attack(object):

  def __init__(self, bot):
    self.bot = bot  
    self.scout_index = -1
    self.scout_tag = None
    self.attacking = False

  def units_excluding_scout(self):
    def is_not_scout(unit):
      return unit.tag != self.scout_tag
    return self.bot.units(UnitTypeId.MARINE).filter(is_not_scout) | self.bot.units(UnitTypeId.MARAUDER) | self.bot.units(UnitTypeId.MEDIVAC)

  def find_unit_by_tag(self, unit_tag):
    for unit in self.bot.units:
      if unit.tag == unit_tag:
        return unit
    return None

  async def on_step(self, iteration):
    cc = self.bot.units(UnitTypeId.COMMANDCENTER)
    if not cc.exists:
      target = self.bot.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
      for unit in self.bot.workers | self.bot.units(UnitTypeId.MARINE):
        await self.bot.do(unit.attack(target))
      return
    else:
      cc = cc.first

    await self.attack(iteration, cc)
    await self.scout(iteration, cc)

  async def attack(self, iteration, cc):
    if iteration % 4 == 0:
      return

    staging_pick_distance = 15
    reaction_distance = 75

    rally_point = cc.position.towards(self.bot.game_info.map_center, distance=22)

    near_cc_count = self.units_excluding_scout().closer_than(staging_pick_distance, cc.position).amount
    near_rally_count = self.units_excluding_scout().closer_than(staging_pick_distance, rally_point).amount

    base_attackers = self.bot.known_enemy_units.closer_than(15, cc)
    all_enemies = self.bot.known_enemy_units + self.bot.known_enemy_structures + self.bot.enemy_start_locations
    all_units = self.units_excluding_scout()

    if self.attacking and iteration % 10 == 0:
      for unit in all_units:
        enemy_units = self.bot.units.enemy.prefer_close_to(unit.position)[:0]
        if len(enemy_units) > 0:
          await self.bot.do(unit.attack(self.bot.units.enemy.prefer_close_to(unit.position)[:0]))
        elif len(all_enemies) > 0:
          await self.bot.do(unit.attack(all_enemies[0]))

    if base_attackers.amount > 3 and iteration % 10 == 0:
      for unit in self.units_excluding_scout() | self.bot.units(UnitTypeId.SCV):
        await self.bot.do(unit.attack(base_attackers[0].position))

    elif self.bot.known_enemy_units.amount > 0 and (near_cc_count + near_rally_count > 50) and iteration % 5 == 0:
      closest_enemy = self.bot.known_enemy_units.closest_to(cc)
      for unit in self.units_excluding_scout().closer_than(reaction_distance, closest_enemy):
        await self.bot.do(unit.attack(closest_enemy))

    elif near_cc_count > 5 and iteration % 5 == 0:
      for unit in self.units_excluding_scout().closer_than(staging_pick_distance, cc.position):
        await self.bot.do(unit.attack(rally_point))

    elif self.units_excluding_scout().amount > 40:
      self.attacking = True
      target = self.bot.known_enemy_structures.random_or(self.bot.enemy_start_locations[0]).position
      if len(all_enemies) > 0:
        print(f'Over limit units and late enough -> ATTACK')
        for unit in all_units:
          await self.bot.do(unit.attack(target))
      # elif iteration % 30 == 0:
      #   print(f'Spreadscout time!')
      #   # No known enemies - try to find some
      #   for unit in all_units:
      #     await self.do(unit.attack(unit.position.towards_random_angle(cc.position, max_difference=2*pi, distance=45)))

    elif iteration % 20 == 0:
      # Rally up
      for unit in self.units_excluding_scout():
        await self.bot.do(unit.attack(rally_point))

  async def scout(self, iteration, cc):

    # Retreat if enemies
    scout = self.find_unit_by_tag(self.scout_tag)
    if scout and self.bot.known_enemy_units.closer_than(50, scout.position):
      print(f'Retreating!')
      await self.bot.do(scout.move(cc.position))

    if not iteration % 150 == 0:
      return

    print(f'Found scout {scout}')

    if scout == None:
      # Assign scout if available
      if self.bot.units(UnitTypeId.MARINE).idle.amount > 3:
        marine = self.bot.units(UnitTypeId.MARINE).first
        print(f'Assigned marine {marine.tag} to scout')
        self.scout_tag = marine.tag
        scout = marine

    # Scout
    if scout:
      print(f'Scouting with {scout}')
      enemy_positions = [x.position for x in self.bot.enemy_start_locations]
      expansion_positions = [x.position for x in self.bot.expansion_locations]
      scout_set = enemy_positions + expansion_positions

      if len(scout_set) > 0:
        self.scout_index = (self.scout_index + 1) % len(scout_set)
        print(f'Next scout target index: {self.scout_index} from {len(scout_set)}')
        await self.bot.do(scout.attack(scout_set[self.scout_index]))
      else:
        print(f'No scoutable area, doing random scouting')
        await self.bot.do(scout.attack(scout.position.towards_random_angle(cc.position, max_difference=2*pi, distance=45)))

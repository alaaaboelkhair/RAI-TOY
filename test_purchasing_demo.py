"""Business-rule regression checks that do not require a Snowflake connection."""
import unittest
from copy import deepcopy
from purchasing_demo import generate, validate_inputs, oracle_cost, lowest_price_first, evaluate_orders, SNAPSHOT, END


class PurchasingRulesTests(unittest.TestCase):
    def setUp(self):
        self.data = generate(list(range(1001, 1031)))

    def test_receipts_respect_dates_and_status(self):
        rows = self.data['incoming_orders']
        self.assertTrue(any(r['EXPECTED_RECEIPT_DATE'] <= SNAPSHOT for r in rows))
        self.assertTrue(any(r['EXPECTED_RECEIPT_DATE'] > END for r in rows))
        self.assertTrue(any(r['STATUS'] == 'cancelled' for r in rows))
        for r in rows:
            if r['STATUS'] != 'confirmed' or not SNAPSHOT < r['EXPECTED_RECEIPT_DATE'] <= END:
                self.assertEqual(r['COUNTED_QTY'], 0)

    def test_missing_lead_and_late_offers_cannot_supply(self):
        missing = [o for o in self.data['offers'] if o['LEAD_TIME_DAYS'] < 0]
        self.assertTrue(missing)
        self.assertTrue(all(o['ELIGIBLE_PACKS'] == 0 and o['EXPECTED_ARRIVAL_DATE'] is None for o in missing))
        self.assertTrue(all(o['ELIGIBLE_PACKS'] == 0 for o in self.data['offers'] if o['PRODUCT_ID'] == 2))
        self.assertEqual(self.data['needs'][1]['UNAVOIDABLE_SHORTFALL_QTY'], 64)

    def test_early_commitment_is_visible_and_included_in_demand(self):
        need = self.data['needs'][0]
        self.assertEqual(need['EARLY_SHORTFALL_QTY'], 15)
        self.assertLessEqual(need['EARLY_DEMAND_QTY'], need['REMAINING_DEMAND_QTY'])
        self.assertEqual(need['REQUIRED_QTY'], 40)

    def test_oracle_accounts_for_pack_and_minimum_order(self):
        # Cheapest piece price would cost 120 because of MOQ. Higher piece price
        # in a smaller pack costs 40 and is the minimum-cost feasible choice.
        data = {'offers': [
            dict(PRODUCT_ID=1, PACK_SIZE=12, MINIMUM_ORDER_QTY=120, ELIGIBLE_PACKS=10,
                 UNIT_COST_CENTS=1, FREIGHT_CENTS_PER_UNIT=0),
            dict(PRODUCT_ID=1, PACK_SIZE=5, MINIMUM_ORDER_QTY=5, ELIGIBLE_PACKS=10,
                 UNIT_COST_CENTS=2, FREIGHT_CENTS_PER_UNIT=0)]}
        self.assertEqual(oracle_cost(data, 1, 20), 40)

    def test_invalid_reservations_and_receipt_credit_are_rejected(self):
        invalid = deepcopy(self.data)
        invalid['inventory'][0]['RESERVED_QTY'] = 99999
        with self.assertRaises(AssertionError):
            validate_inputs(invalid)
        invalid = deepcopy(self.data)
        late = next(r for r in invalid['incoming_orders'] if r['EXPECTED_RECEIPT_DATE'] > END)
        late['COUNTED_QTY'] = late['QUANTITY']
        with self.assertRaises(AssertionError):
            validate_inputs(invalid)

    def test_baseline_matches_achievable_coverage_and_excludes_invalid_offers(self):
        orders = lowest_price_first(self.data)
        rows = evaluate_orders(self.data,orders)
        self.assertEqual(sum(r['DEMAND_SHORTFALL_QTY'] for r in rows),49)
        self.assertEqual(sum(r['SAFETY_SHORTFALL_QTY'] for r in rows),15)
        self.assertFalse(any(a['PRODUCT_ID']==2 for a in orders))
        reversed_data = deepcopy(self.data)
        reversed_data['offers'].reverse()
        self.assertEqual(orders,lowest_price_first(reversed_data))

    def test_baseline_cheapest_unit_price_can_cost_more_due_to_moq(self):
        data = deepcopy(self.data)
        data['products'] = [dict(PRODUCT_ID=1,SAFETY_STOCK_QTY=0)]
        data['needs'] = [dict(PRODUCT_ID=1,REQUIRED_QTY=10,UNAVOIDABLE_SHORTFALL_QTY=0,
                              AVAILABLE_QTY=0,COUNTED_RECEIPTS_QTY=0,REMAINING_DEMAND_QTY=10)]
        template = data['offers'][0]
        data['offers'] = [dict(template,OFFER_ID=1,SUPPLIER_ID=1,PACK_SIZE=6,MINIMUM_ORDER_QTY=24,
                               ELIGIBLE_PACKS=10,CONFIRMED_CAPACITY_QTY=60,UNIT_COST_CENTS=100,FREIGHT_CENTS_PER_UNIT=0),
                          dict(template,OFFER_ID=2,SUPPLIER_ID=2,PACK_SIZE=5,MINIMUM_ORDER_QTY=5,
                               ELIGIBLE_PACKS=10,CONFIRMED_CAPACITY_QTY=50,UNIT_COST_CENTS=150,FREIGHT_CENTS_PER_UNIT=0)]
        orders = lowest_price_first(data)
        self.assertEqual(orders[0]['QUANTITY'],24)
        self.assertEqual(evaluate_orders(data,orders)[0]['TOTAL_COST_CENTS'],2400)
        self.assertEqual(oracle_cost(data,1,10),1500)

    def test_baseline_uses_next_supplier_when_cheapest_capacity_is_exhausted(self):
        data = deepcopy(self.data)
        data['products'] = [dict(PRODUCT_ID=1,SAFETY_STOCK_QTY=0)]
        data['needs'] = [dict(PRODUCT_ID=1,REQUIRED_QTY=20,UNAVOIDABLE_SHORTFALL_QTY=0,
                              AVAILABLE_QTY=0,COUNTED_RECEIPTS_QTY=0,REMAINING_DEMAND_QTY=20)]
        template = data['offers'][0]
        data['offers'] = [dict(template,OFFER_ID=1,SUPPLIER_ID=1,PACK_SIZE=6,MINIMUM_ORDER_QTY=6,
                               ELIGIBLE_PACKS=2,CONFIRMED_CAPACITY_QTY=12,UNIT_COST_CENTS=100,FREIGHT_CENTS_PER_UNIT=0),
                          dict(template,OFFER_ID=2,SUPPLIER_ID=2,PACK_SIZE=5,MINIMUM_ORDER_QTY=5,
                               ELIGIBLE_PACKS=2,CONFIRMED_CAPACITY_QTY=10,UNIT_COST_CENTS=150,FREIGHT_CENTS_PER_UNIT=0)]
        orders = lowest_price_first(data)
        self.assertEqual([a['QUANTITY'] for a in orders],[12,10])
        self.assertEqual(evaluate_orders(data,orders)[0]['DEMAND_SHORTFALL_QTY'],0)


if __name__ == '__main__':
    unittest.main()

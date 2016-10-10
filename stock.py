# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import logging
from dateutil import relativedelta
from sql import From, Join, Null, Select, Table, Union

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['Lot', 'Move']


class Lot:
    __name__ = 'stock.lot'
    __metaclass__ = PoolMeta
    active = fields.Boolean('Active')

    @staticmethod
    def default_active():
        return True

    @classmethod
    def deactivate_lots_without_stock(cls, lots=None, margin_days=1):
        '''Deactivate lots that doesn't have stock after <margin_days> nor any
        pending move'''
        pool = Pool()
        Date = pool.get('ir.date')
        Location = pool.get('stock.location')
        Move = pool.get('stock.move')

        move = Move.__table__()

        assert isinstance(margin_days, int) and margin_days >= 0

        locations = Location.search([
                ('parent.type', '=', 'warehouse'),
                ('type', '=', 'storage'),
                ])
        stock_end_date = Date.today() - relativedelta.relativedelta(
            days=margin_days)

        # lots with done moves after margin_days or any pending moves
        query = move.select(move.lot,
            where=((move.lot != Null)
                & (
                    ((move.state == 'done')
                        & (move.effective_date > stock_end_date))
                    | ~move.state.in_(['cancel', 'done'])
                    )
                ),
            group_by=(move.lot,))

        domain = [
            ('id', 'not in', query),
            ('quantity', '=', 0),
            ]
        if lots:
            domain.insert(0, ('id', 'in', [l.id for l in lots]))

        with Transaction().set_context(locations=[l.id for l in locations],
                stock_date_end=stock_end_date):
            lots = cls.search(domain)
        logging.getLogger(cls.__name__).info("Deactivating %s lots", len(lots))
        if lots:
            cls.write(lots, {'active': False})


class Move:
    __name__ = 'stock.move'
    __metaclass__ = PoolMeta

    @classmethod
    def compute_quantities_query(cls, location_ids, with_childs=False,
            grouping=('product',), grouping_filter=None):
        pool = Pool()
        Lot = pool.get('stock.lot')
        Period = pool.get('stock.period')

        query = super(Move, cls).compute_quantities_query(
            location_ids, with_childs=with_childs, grouping=grouping,
            grouping_filter=grouping_filter)
        if not query or 'lot' not in grouping:
            return query

        tables_to_find = [cls._table]
        for grouping in Period.groupings():
            Cache = Period.get_cache(grouping)
            if Cache:
                tables_to_find.append(Cache._table)

        def find_table(join):
            if not isinstance(join, Join):
                return
            for pos in ['left', 'right']:
                item = getattr(join, pos)
                if isinstance(item, Table):
                    if item._name in tables_to_find:
                        return getattr(join, pos)
                else:
                    return find_table(item)

        def find_queries(query):
            if isinstance(query, Union):
                for sub_query in query.queries:
                    for q in find_queries(sub_query):
                        yield q
            elif isinstance(query, Select):
                yield query

        lot = Lot.__table__()
        union, = query.from_
        for sub_query in find_queries(union):
            # Find move table
            new_from_list = []
            for table in sub_query.from_:
                if (isinstance(table, Table)
                        and table._name in tables_to_find):
                    new_from_list.append(
                        table.join(lot,
                            condition=(table.lot == lot.id)))
                    break
                found = find_table(table)
                if found:
                    new_from_list.append(
                        table.join(lot,
                            condition=(found.lot == lot.id)))
                    break
                new_from_list.append(table)
            else:
                # Not query on move table
                continue

            sub_query.from_ = From()
            for new_from in new_from_list:
                sub_query.from_.append(new_from)
            sub_query.where &= (lot.active == True)
        return query

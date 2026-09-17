from decimal import Decimal

from app.portfolio.schemas import PaperOrderCreate
from app.portfolio.service import PortfolioService
from app.trading.orders import client_order_id


class TradingExecutor:
    def __init__(self, repository):
        self.portfolio = PortfolioService(repository, None)

    def fill(self, c, row, config, event_key, side, quantity, price):
        request = PaperOrderCreate(client_order_id=client_order_id(row['bot_id'], event_key),
                                   symbol=config.symbol.split('/')[0], side=side,
                                   quantity=quantity, simulation_price=price, fee=Decimal('0'))
        order = self.portfolio.reserve_in_transaction(c, row['user_id'], config.portfolio_id, request, managed=True)
        return self.portfolio.complete_in_transaction(c, row['user_id'], config.portfolio_id, order['order_id'], 'fill')

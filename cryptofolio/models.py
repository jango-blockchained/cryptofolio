# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.db import models

from encrypted_model_fields.fields import EncryptedCharField

from .api.API import API
from .api.Config import get_default_fiat_name
from .api.BalanceFromAddress import BalanceFromAddress


class Fiat(models.Model):
    name = models.CharField(max_length=10, primary_key=True)

    def __str__(self):
        return "%s" % (self.name)


class Currency(models.Model):
    name = models.CharField(max_length=10, primary_key=True)

    def __str__(self):
        return "%s" % (self.name)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    fiat = models.CharField(max_length=10, default=get_default_fiat_name())

    def __str__(self):
        return "%s %s" % (self.user, self.fiat)


class Rates(models.Model):
    currency = models.CharField(max_length=10, default='BTC')
    fiat = models.CharField(
        max_length=10, default=get_default_fiat_name(), db_index=True)
    rate = models.FloatField(default=None, blank=True, null=True)

    def __str__(self):
        return "%s %s %s" % (self.currency, self.fiat, self.rate)

class Exchange(models.Model):
    name = models.CharField(max_length=100, primary_key=True)
    label = models.CharField(max_length=100, null=True)

    def __str__(self):
        return "%s %s" % (self.name, self.label)


class ExchangeAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE)
    key = EncryptedCharField(max_length=1024)
    secret = EncryptedCharField(max_length=1024)
    passphrase = EncryptedCharField(
        max_length=1024,
        default=None,
        blank=True,
        null=True,
        help_text='<ul><li>Optional</li></ul>')

    def __str__(self):
        return "%s %s" % (self.user.username, self.exchange.label)


class ExchangeBalance(models.Model):
    exchange_account = models.ForeignKey(
        ExchangeAccount,
        on_delete=models.CASCADE
    )
    currency = models.CharField(max_length=10, default='BTC')
    amount = models.FloatField(default=None, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "%s %s %s" % (
            self.exchange_account,
            self.currency,
            self.timestamp)


class ManualInput(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    currency = models.CharField(max_length=10, default='BTC')
    amount = models.FloatField(default=None, blank=True, null=True)

    def __str__(self):
        return "%s %s %s %s" % (self.user.username, self.timestamp,
                                self.currency, self.amount)


class AddressInput(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    currency = models.CharField(max_length=10, default='BTC')
    address = models.CharField(max_length=100)
    amount = models.FloatField(default=None, blank=True, null=True)

    def __str__(self):
        return "%s %s %s %s %s" % (self.user.username, self.timestamp,
                                   self.currency, self.address, self.amount)

class Investment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.FloatField(default=None, blank=True, null=True)
    fiat = models.CharField(max_length=10, default=get_default_fiat_name())
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "%s %s %s %s" % (self.user.username, self.amount, self.fiat.name,
                                self.timestamp)

class TimeSeries(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    amount = models.FloatField(default=None, blank=True, null=True)
    fiat = models.CharField(max_length=10, default=get_default_fiat_name())

    def __str__(self):
        return "%s %s %s %s" % (self.user.username, self.timestamp,
                                self.amount, self.fiat)


class BalanceTimeSeries(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    amount = models.FloatField(default=None, blank=True, null=True)
    currency = models.CharField(max_length=10, default='BTC')
    fiat = models.CharField(max_length=10, default=get_default_fiat_name())

    def __str__(self):
        return "%s %s %s %s" % (self.user.username, self.timestamp,
                                self.amount, self.currency)


def update_exchange_balances(exchange_accounts):
    has_errors = False
    errors = []
    for exchange_account in exchange_accounts:
        api = API(exchange_account)
        balances, error = api.getBalances()

        if error:
            has_errors = True
            errors.append(error)
        else:
            exchange_balances = ExchangeBalance.objects.filter(
                exchange_account=exchange_account)

            for currency in balances:
                exchange_balance, created = ExchangeBalance.objects.get_or_create(
                    exchange_account=exchange_account,
                    currency=currency)

                exchange_balance.amount = balances[currency]
                exchange_balance.save()

            for exchange_balance in exchange_balances:
                currency = exchange_balance.currency
                if currency not in balances:
                    exchange_balance.delete()

    return (has_errors, errors)

def update_address_input_balances(user):
    address_api = BalanceFromAddress()
    address_inputs = AddressInput.objects.filter(user=user)

    result = address_api.getBalances(address_inputs)

    for address_input in address_inputs:
        address_input.amount = result[address_input.address]
        address_input.save()


def get_aggregated_balances(exchange_accounts, manual_inputs, address_inputs):
    crypto_balances = {}
    for exchange_account in exchange_accounts:
        exchange_balances = ExchangeBalance.objects.filter(
            exchange_account=exchange_account)

        # aggregate latest balances
        for exchange_balance in exchange_balances:
            currency = exchange_balance.currency
            amount = exchange_balance.amount

            if amount is None:
                continue
            if currency in crypto_balances:
                crypto_balances[currency] += amount
            else:
                crypto_balances[currency] = amount

    for manual_input in manual_inputs:
        currency = manual_input.currency
        amount = manual_input.amount

        if amount is None:
            continue
        if currency in crypto_balances:
            crypto_balances[currency] += amount
        else:
            crypto_balances[currency] = amount

    for address_input in address_inputs:
        currency = address_input.currency
        amount = address_input.amount

        if amount is None:
            continue
        if currency in crypto_balances:
            crypto_balances[currency] += amount
        else:
            crypto_balances[currency] = amount

    return crypto_balances


def convert_to_fiat(crypto_balances, fiat):
    balances = []
    other_balances = []
    rates = Rates.objects.filter(fiat=fiat)

    # Manually handle glitches
    name_conversions = { "MIOTA" : "IOTA" }

    currency_to_rate = {}
    for rate in rates:
        currency_to_rate[rate.currency] = rate.rate
        if rate.currency in name_conversions:
            currency_to_rate[name_conversions[rate.currency]] = rate.rate

    for currency in crypto_balances:
        if currency in currency_to_rate:
            try:
                balances.append({
                    'currency': currency,
                    'amount': crypto_balances[currency],
                    'amount_fiat':
                        crypto_balances[currency] * currency_to_rate[currency]
                })
            except TypeError as e:
                pass

        elif currency == fiat:
            balances.append(
                {
                    'currency': currency,
                    'amount': crypto_balances[currency],
                    'amount_fiat': crypto_balances[currency],
                }
            )
        else:
            other_balances.append(
                {
                    'currency': currency,
                    'amount': crypto_balances[currency]
                }
            )

    return (balances, other_balances)

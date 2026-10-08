import getpass
from argon2 import PasswordHasher
print(PasswordHasher().hash(getpass.getpass('Mot de passe: ')))

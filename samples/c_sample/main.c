/* C sample: Sieve of Eratosthenes — finds all primes up to N */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LIMIT 100

int main(void) {
    char sieve[LIMIT + 1];
    memset(sieve, 1, sizeof(sieve));
    sieve[0] = sieve[1] = 0;

    for (int i = 2; i * i <= LIMIT; i++) {
        if (sieve[i]) {
            for (int j = i * i; j <= LIMIT; j += i)
                sieve[j] = 0;
        }
    }

    printf("=== C Sample: Sieve of Eratosthenes (primes up to %d) ===\n", LIMIT);

    int count = 0;
    FILE *out = fopen("primes.txt", "w");
    if (!out) { perror("fopen"); return 1; }

    for (int i = 2; i <= LIMIT; i++) {
        if (sieve[i]) {
            printf("%d ", i);
            fprintf(out, "%d\n", i);
            count++;
        }
    }
    printf("\n\nFound %d primes. Written to primes.txt\n", count);
    fclose(out);
    return 0;
}

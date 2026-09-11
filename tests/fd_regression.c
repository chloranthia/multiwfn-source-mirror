#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "2F2.h"

struct regression_case {
  const char *name;
  double a1;
  double a2;
  double b1;
  double b2;
  double z;
  double expected;
};

int main(void) {
  /* These parameters match the 2F2 terms used for alpha=0.5 and p=1:
     a1=n+1, a2=n+2, b1=n+1.5, b2=n+2.5. */
  const struct regression_case cases[] = {
      {"s-type term", 1.0, 2.0, 1.5, 2.5, -0.75,
       0.6858968604554676067},
      {"higher angular term", 3.0, 4.0, 3.5, 4.5, -2.0,
       0.2356634227907346796},
  };
  const double tolerance = 5e-13;

  for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    const struct regression_case *test = &cases[i];
    const double actual =
        hyp2F2(test->a1, test->a2, test->b1, test->b2, test->z);
    if (!isfinite(actual) || fabs(actual - test->expected) > tolerance) {
      fprintf(stderr, "%s: got %.17g, expected %.17g (tolerance %.1e)\n",
              test->name, actual, test->expected, tolerance);
      return EXIT_FAILURE;
    }
  }

  puts("Fractional-derivative 2F2 regression passed");
  return EXIT_SUCCESS;
}

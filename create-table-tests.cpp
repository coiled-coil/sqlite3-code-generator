#define BOOST_TEST_MAIN
#include <boost/test/unit_test.hpp>
// #include <boost/test/included/unit_test.hpp>
#include "tmp/db.hpp"

struct my_handler
{
    int operator()(int ret, const char *name = NULL, int id = 0)
    {
        return true;
    }
};

BOOST_AUTO_TEST_CASE( test1 )
{
    //BOOST_CHECK_EQUAL
    //SQLITE_OK

    sqlite3 *db = NULL;
    query_something(db, 1, my_handler());
}

